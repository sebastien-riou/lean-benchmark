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

def describe_results(data,*,details=True) -> str:
    out = io.StringIO()
    def p(s):
        print(s,file=out)
    info = data['info']
    results = data['results']
    for i in range(0,len(info),2) :
        p(f'{info[i]}: {info[i+1]}')
    nresults = len(results)
    p(f'{nresults} records')
    consolidated = {}
    for r in results:
        info=r['setup info']
        case_index=r.get('case_index',0)
        cycles = get_cycles(r['data'])
        min_cycles = min(cycles)
        max_cycles = max(cycles)
        ave_cycles = math.ceil(sum(cycles)/len(cycles))
        key = f'{info['dut name']}-{info['args setup name']}'
        if key not in consolidated:
            consolidated[key]=[]
        consolidated[key].append({'min_cycles':min_cycles,'max_cycles':max_cycles,'ave_cycles':ave_cycles})
        
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
                stack_size = f'{humanfriendly.format_size(t['stack size'],binary=True)} ({t['stack size']} bytes)'
                stack += stack_size
                p(f'\t{format_number(t['cycles'],exact_in_brackets=True)} cycles, {stack} of stack')
                extra_data = t['extra data']
                for d in extra_data:
                    p(f'\t\t{d[0]}:{Utils.hexstr(d[1])}')
    
    for key,val in consolidated.items():
        min_cycles = min([v['min_cycles'] for v in val])
        max_cycles = max([v['max_cycles'] for v in val])
        ave_cycles = math.ceil(sum([v['ave_cycles'] for v in val])/len(val))
        p(f'Consolidated stats for {key}:')
        p(f'\tMin cycles: {format_number(min_cycles)}')
        p(f'\tAve cycles: {format_number(ave_cycles)}')
        p(f'\tMax cycles: {format_number(max_cycles)}')

    return out.getvalue()

def get_cycles(data, *, sort=False):
    out = []
    for t in data:
        out.append(t['cycles'])
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
    
    
    args = parser.parse_args()

    if args.describe:
        with open(args.describe,'rb') as f:
            results = pickle.load(f)
            print(describe_results(results))
        sys.exit()

    if args.device is None and args.uart_log is None:
        parser.print_help()
        exit(-1)


    logformat = '%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s'
    logdatefmt = '%Y-%m-%d %H:%M:%S'
    logging.basicConfig(level=args.log_level, format=logformat, datefmt=logdatefmt)
    
    
    if args.device:
        source = serial.Serial(args.device, exclusive=args.exclusive,baudrate=args.baud)
        source.write(bytes(1))
        timestamp = None #we will generate timestamps during the processing
    else:
        # we use the timestamp from OS (last modification timestamp)
        timestamp = os.path.getmtime(args.uart_log)
        source = open(args.uart_log,'rb') 

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

    read_lines_until(b'lean-benchmark start')
    
    def read_u32() -> int:
        b = source.read(4)
        out = int.from_bytes(b,byteorder='little')
        logging.debug(f'read_u32: {out}')
        return out

    def read_string() -> str:
        size = read_u32()  
        out = source.read(size).decode('utf-8')
        logging.debug(f'read_string: "{out}"')
        return out

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
            extra_data = list()
            for j in range(0,nextra_data):
                #get extra data
                name = read_string()
                length = read_u32()
                v = source.read(length)
                extra_data.append([name,v])
            results_data.append({'cycles':cycles, 'stack size':stack, 'extra data':extra_data})
        result['data'] = results_data
        results.append(result)
    out = {'info':info,'results':results}
    if args.write_pickle != 0:
        name = build_pickle_file_name(get_timestamp(timestamp),info)
        if timestamp is None:#avoid overwriting results (unless timestamp was comming from uart-log file)
            while os.path.exists(name):
                name = build_pickle_file_name(get_timestamp(),info) 
        with open(name,'wb') as f:
            pickle.dump(out,f)
    print(describe_results(out,details=args.details))
        
