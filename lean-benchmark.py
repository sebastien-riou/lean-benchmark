import datetime
import serial 
import sys,os,argparse
from pysatl import Utils
import logging
import io
import pickle

def timestamp() -> str:
    now = datetime.datetime.now()
    return now.strftime('%Y%m%d-%H-%M-%S')

def describe_results(results) -> str:
    out = io.StringIO()
    def p(s):
        print(s,file=out)
    nresults = len(results)
    p(f'{nresults} records')
    for r in results:
        info=r['setup info']
        p(f'{r['timestamp']}: {info['dut name']} with {info['args setup name']}, {info['ntrials']} trials')
        for t in r['data']:
            stack = ''
            if t['stack size'] == info['max stack size']:
                stack = 'more than '
            stack += f'{t['stack size']}'
            p(f'\t{t['cycles']} cycles, {stack} bytes of stack')
            extra_data = t['extra data']
            for d in extra_data:
                p(f'\t\t{d[0]}:{Utils.hexstr(d[1])}')

    return out.getvalue()

if __name__ == '__main__':
    scriptname = os.path.basename(__file__)
    parser = argparse.ArgumentParser(scriptname)
    levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    parser.add_argument('--log-level', default='DEBUG', choices=levels)
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
    
    args = parser.parse_args()

    if args.describe:
        with open(args.describe,'rb') as f:
            results = pickle.load(f)
            print(describe_results(results))
        sys.exit()

    device_path = args.device

    logformat = '%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s'
    logdatefmt = '%Y-%m-%d %H:%M:%S'
    logging.basicConfig(level=args.log_level, format=logformat, datefmt=logdatefmt)
    
    with serial.Serial(device_path, exclusive=args.exclusive,baudrate=args.baud) as device:

        def read_lines_until(expected,log_level=logging.DEBUG) -> bytes:
            out = bytearray()
            while True:
                line = device.readline()
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
            b = device.read(4)
            out = int.from_bytes(b,byteorder='little')
            logging.debug(f'read_u32: {out}')
            return out

        def read_string() -> str:
            size = read_u32()  
            out = device.read(size).decode('utf-8')
            logging.debug(f'read_string: "{out}"')
            return out

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
            result = dict()
            result['timestamp'] = timestamp()
            result['setup info'] = setup_info
            results_data = list()
            for i in range(0,setup_info['ntrials']):
                cycles = read_u32()
                stack  = read_u32()
                extra_data = list()
                for j in range(0,nextra_data):
                    #get extra data
                    name = read_string()
                    length = read_u32()
                    v = device.read(length)
                    extra_data.append([name,v])
                results_data.append({'cycles':cycles, 'stack size':stack, 'extra data':extra_data})
            result['data'] = results_data
            results.append(result)
        with open(f'{timestamp()}-lean-benchmark.pickle','wb') as f:
            pickle.dump(results,f)
        print(describe_results(results))
        
