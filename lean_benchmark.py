import datetime
import serial 
import sys,os,argparse
from pysatl import Utils
import logging
import io
import pickle
import math
import humanfriendly

def get_timestamp(ts=None) -> str:
    if ts:
        dt = datetime.datetime.fromtimestamp(ts)
    else:
        dt = datetime.datetime.now()
    return dt.strftime('%Y%m%d-%H-%M-%S')

def format_number(num: int, *,precision=1,exact_in_brackets=False) -> str:
    units={'K':10**3,'M':10**6,'G':10**9}
    for u in ['G','M','K']:
        divider = units[u]
        if num > divider:
            r = num/divider
            out = f'{r:.{precision}f}{u}'
            if exact_in_brackets:
                out += f' ({num})'
            return out
    return f'{num}'

def format_timestamp(seconds: float,*,precision=1) -> str:
    units={'s':1,'ms':10**3,'us':10**6,'ns':10**9}
    for u in ['ms','us','ns']:
        divider = units[u]
        r = round(seconds*divider)
        if r > 0:
            out = f'{seconds*divider:.{precision}f}{u}'
            return out
    return f'{seconds} s'

def format_size(size) -> str:
    out = f'{humanfriendly.format_size(size,binary=True)}'
    if size > 0:
        out += f' ({size} bytes)'
    return out

def describe_results(data,*,details=True) -> str:
    out = io.StringIO()
    def p(s):
        print(s,file=out)
    info = data['info']
    results = data['results']
    for i in range(0,len(info),2) :
        p(f'{info[i]}: {info[i+1]}')

    keys = data['info'][::2] #items at even index
    values = data['info'][1::2] #items at odd index
    info = dict(zip(keys,values))

    logging.debug(info)
    frequency = None
    if 'frequency_mhz' in info.keys():
        frequency = float(info['frequency_mhz']) * 1000 * 1000

    nresults = len(results)
    p(f'{nresults} records')
    consolidated = {}
    heap_reported = True
    for r in results:
        info=r['setup info']
        case_index=r.get('case_index',0)
        cycles = get_field(r['data'],'cycles')
        min_cycles = min(cycles)
        max_cycles = max(cycles)
        ave_cycles = math.ceil(sum(cycles)/len(cycles))
        stack_sizes = get_field(r['data'],'stack size')
        max_stack = max(stack_sizes)
        try:
            heap_sizes = get_field(r['data'],'heap size')
            max_heap = max(heap_sizes)
        except:
            max_heap = 0
            heap_reported = False
        key = f'{info['dut name']}-{info['args setup name']}'
        if key not in consolidated:
            consolidated[key]=[]
        consolidated[key].append({'min_cycles':min_cycles,'max_cycles':max_cycles,'ave_cycles':ave_cycles,'max_stack':max_stack,'max_heap':max_heap})
        
        if details:
            p(f'{r['timestamp']}: {info['dut name']} with {info['args setup name']}, {info['ntrials']} trials, case {case_index}')
            p(f'\tMin cycles: {min_cycles}')
            p(f'\tAve cycles: {ave_cycles}')
            p(f'\tMax cycles: {max_cycles}')
            p(f'\tMax-Min: {max_cycles-min_cycles}')
            for t in r['data']:
                stack = ''
                if t['stack size'] == info['max stack size']:
                    stack = 'more than '
                stack_size = format_size(t['stack size'])
                stack += stack_size
                msg = f'\t{format_number(t['cycles'],exact_in_brackets=True)} cycles, {stack} of stack'
                if heap_reported:
                    heap = format_size(t['heap size'])
                    msg+=f', {heap} of heap'
                p(msg)
                extra_data = t['extra data']
                for d in extra_data:
                    p(f'\t\t{d[0]}:{Utils.hexstr(d[1])}')
    
    for key,val in consolidated.items():
        min_cycles = min([v['min_cycles'] for v in val])
        max_cycles = max([v['max_cycles'] for v in val])
        ave_cycles = math.ceil(sum([v['ave_cycles'] for v in val])/len(val))
        max_stack = max([v['max_stack'] for v in val])
        max_heap = max([v['max_heap'] for v in val])
        t_min_str = ''
        t_ave_str = ''
        t_max_str = ''
        if frequency:
            t_min = min_cycles/frequency
            t_ave = ave_cycles/frequency
            t_max = max_cycles/frequency
            #t_min_str = f' ({humanfriendly.format_timespan(t_min)})' #not good for sub seconds :-(
            #t_ave_str = f' ({humanfriendly.format_timespan(t_ave)})'
            #t_max_str = f' ({humanfriendly.format_timespan(t_max)})'
            t_min_str = f' ({format_timestamp(t_min)})'
            t_ave_str = f' ({format_timestamp(t_ave)})'
            t_max_str = f' ({format_timestamp(t_max)})'
        p(f'Consolidated stats for {key}:')
        p(f'\tMin cycles: {format_number(min_cycles)}{t_min_str}')
        p(f'\tAve cycles: {format_number(ave_cycles)}{t_ave_str}')
        p(f'\tMax cycles: {format_number(max_cycles)}{t_max_str}')
        p(f'\tMax stack:  {format_size(max_stack)}')
        if heap_reported:
            p(f'\tMax heap:   {format_size(max_heap)}')
        else:
            p(f'\tHeap not reported')
        
    return out.getvalue()

def get_field(data, field, *, sort=False):
    out = []
    for t in data:
        out.append(t[field])
    if sort:
        out.sort()
    return out

def build_pickle_file_name(ts,info):
    description = 'lean-benchmark'
    values = info[1::2] # keep only elements at odd indexes (we expect constant labels at even indexes)
    last = len(values)
    if last > 0:
        while True:
            description = '-'.join(values[:last])
            if len(description) < 256:
                break
            last -= 1
        description = "".join(x if (x.isalnum() or x in "._- ") else '-' for x in description )
    return f'{ts}-{description}.pickle'

class DeviceRuntimeError(RuntimeError):
    pass

class SerialWithException():
    EXCEPTION = "EXCEPTION".encode()
    def __init__(self, impl):
        self.impl = impl
        self.threshold = len(self.EXCEPTION)
        self.level=0
        self.all = bytearray()

    def read1(self):
        c = self.impl.read(1)
        self.all += c
        e = self.EXCEPTION[self.level]
        i = c[0]
        if i == e:
            self.level+=1
            if self.level == self.threshold:
                self.level = 0
                raise DeviceRuntimeError()
        else:
            self.level = 0
        return c
    
    def read(self, n):
        out = bytearray()
        for i in range(0,n):
            out += self.read1()
        return bytes(out)

    def readline(self):
        out = bytearray()
        while(True):
            c = self.read1()
            out += c
            if c == b'\n':
                return bytes(out)
    
    def write(self, data):
        self.impl.write(data)

if __name__ == '__main__':
    scriptname = os.path.basename(__file__)
    parser = argparse.ArgumentParser(scriptname)
    levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    parser.add_argument('--log-level', default='INFO', choices=levels)
    parser.add_argument(
        '--device', help='Path to the serial device', type=str
    )
    parser.add_argument(
        '--baud', default=115200, help='Baudrate', type=int
    )
    parser.add_argument(
        '--exclusive', help='Exclusive access', action='store_true'
    )
    parser.add_argument(
        '--describe', default=None, help='Path to pickle file', type=str
    )
    parser.add_argument(
        '--uart-log', default=None, help='Path to raw UART output', type=str
    )
    parser.add_argument(
        '--details', help='Show all details', default=1, type=int
    )
    parser.add_argument(
        '--write-pickle', help='Write pickle file', default=1, type=int
    )
    parser.add_argument(
        '--send', help='send', default=None, type=str
    )
    
    
    
    args = parser.parse_args()

    logformat = '%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s'
    logdatefmt = '%Y-%m-%d %H:%M:%S'
    logging.basicConfig(level=args.log_level, format=logformat, datefmt=logdatefmt)
    
    if args.describe:
        with open(args.describe,'rb') as f:
            results = pickle.load(f)
            print(describe_results(results,details=args.details))
        sys.exit()

    if args.device is None and args.uart_log is None:
        parser.print_help()
        exit(-1)
    
    if args.device:
        ser = serial.Serial(args.device, exclusive=args.exclusive,baudrate=args.baud)
        source = SerialWithException(ser)
        if args.send:
            ser.write(Utils.ba(args.send))
            ser.flush()
        timestamp = None #we will generate timestamps during the processing
    else:
        # we use the timestamp from OS (last modification timestamp)
        timestamp = os.path.getmtime(args.uart_log)
        source = SerialWithException(open(args.uart_log,'rb')) 

    def read_lines_until(expected,log_level=logging.DEBUG) -> bytes:
        out = bytearray()
        while True:
            line = source.readline()
            out += line
            line = line.strip()
            try:
                logging.log(level=log_level,msg=line.decode())
            except:
                logging.log(level=log_level,msg=Utils.hexstr(line))
            if(line.endswith(expected)):
                break
        return bytes(out)

    def read_u32() -> int:
        b = source.read(4)
        out = int.from_bytes(b,byteorder='little')
        logging.debug(f'read_u32: {out}')
        return out
    
    def read_u64() -> int:
        b = source.read(8)
        out = int.from_bytes(b,byteorder='little')
        logging.debug(f'read_u64: {out}')
        return out

    def read_string() -> str:
        size = read_u32()  
        out = source.read(size).decode('utf-8')
        logging.debug(f'read_string: "{out}"')
        return out

    try:
        read_lines_until(b'lean-benchmark start')
        
        info = []
        ninfo = read_u32()
        for i in range(0,ninfo):
            info.append(read_string())
        results = list()
        while True:
            setup_info = dict()
            setup_info['dut name'] = read_string()
            if 0 == len(setup_info['dut name']):
                break #end of benchmark
            setup_info['args setup name'] = read_string()
            setup_info['nargs'] = read_u32()
            setup_info['ntrials'] = read_u32()
            setup_info['max stack size'] = read_u32()
            nextra_data = read_u32()
            case_index = read_u32()
            result = dict()
            if timestamp:
                result['timestamp'] = timestamp
            else:
                result['timestamp'] = get_timestamp()
            result['setup info'] = setup_info
            result['case_index'] = case_index
            results_data = list()
            for i in range(0,setup_info['ntrials']):
                cycles = read_u32()
                stack  = read_u32()
                heap   = read_u64()
                extra_data = list()
                for j in range(0,nextra_data):
                    #get extra data
                    name = read_string()
                    length = read_u32()
                    v = source.read(length)
                    extra_data.append([name,v])
                results_data.append({'cycles':cycles, 'stack size':stack, 'heap size': heap, 'extra data':extra_data})
            result['data'] = results_data
            results.append(result)
    except DeviceRuntimeError:
        logging.error("Device raised an exception: press CTRL-C to terminate")
        while(True):
            raw = source.impl.readline()
            try:
                s = raw.decode()
                logging.error(s.strip())
            except:
                logging.error(raw)

    out = {'info':info,'results':results}
    if args.write_pickle != 0:
        name = build_pickle_file_name(get_timestamp(timestamp),info)
        if timestamp is None:#avoid overwriting results (unless timestamp was comming from uart-log file)
            while os.path.exists(name):
                name = build_pickle_file_name(get_timestamp(),info) 
        with open(name,'wb') as f:
            pickle.dump(out,f)
    print(describe_results(out,details=args.details))
        
