#include "lean-benchmark.h"
#include <stdio.h>
#include <stdbool.h>
#define xstr(s) str(s)
#define str(s) #s
void init(int argc, const char*argv[]);

uint8_t extra_data_parity;
uint32_t sum(const uint8_t* const dat, uint32_t size){
  uint32_t out = 0;
  for(uint32_t i=0;i<size;i++){
    out += dat[i];
  }
  extra_data_parity = out & 1;
  return out;
}

uint64_t sum_dut(uintptr_t*args){
  //anything here is part of the benchmark, so it should be just setting arguments
  uintptr_t*argsp = (uintptr_t*)args;
  const uint8_t*const dat = (const uint8_t*const)argsp[0];
  uint32_t size = argsp[1];
  return sum(dat,size);
} 
static uint8_t dat[100];
  
void sum_args_setup(uintptr_t*args){
  LBMK_rng_fill(dat,sizeof(dat));
  args[0] = (uintptr_t)dat;
  args[1] = sizeof(dat);  
}

benchmark_setup_t sum_benchmark_simple_setup = {
  .dut_name = "sum_dut",
  .dut = sum_dut,
  .args_setup_name = "sum_args_setup",
  .args_setup = sum_args_setup,
  .nargs = 2,
  .ntrials = 10,
  .max_stack_size = 2*1024,
  .post_exec = 0,
  .nextra_data = 0
};

void post_exec(tlv_t*extra_data_info, uintptr_t*args,uint64_t output){
  extra_data_info[0].tag = "parity";
  extra_data_info[0].length = 1;
  extra_data_info[0].value = &extra_data_parity;
}

benchmark_setup_t sum_benchmark_setup_with_extra_data = {
  .dut_name = "sum_dut",
  .dut = sum_dut,
  .args_setup_name = "sum_args_setup",
  .args_setup = sum_args_setup,
  .nargs = 2,
  .ntrials = 10,
  .max_stack_size = 2*1024,
  .post_exec = post_exec,
  .nextra_data = 1
};

void sum_custom_benchmark(unsigned int ntrials){
  printf("%s\n",__func__);
  const unsigned int max_stack_size = 1024*2;
  benchmark_result_t results[ntrials];
  for(unsigned int i=0;i<ntrials;i++){
    uintptr_t args[2];
    sum_args_setup(args);
    LBMK_benchmarkit_core(sum_dut,args,sizeof(args),max_stack_size,results+i);
  }
  for(unsigned int i=0;i<ntrials;i++){
    printf("Trial %2u: %10u cycles, %5u bytes on stack\n",i,results[i].cycles, results[i].stack_size);
  }
}

void delay_ms(unsigned int ms);
void com_tx(const void *const buf, unsigned int size);
void LBMK_com_tx(const void*data, unsigned int size){
  com_tx(data,size);
}
int __io_putchar(int ch){//override to get printf on the python output (except on linux)
	return LBMK_putchar(ch);
}

#if 0==RAW_COM
void com_rx(void *const buf, unsigned int size);
void LBMK_com_rx(void*const data, unsigned int size){
  com_rx(data,size);
}
void _leancom_error_handler(uint32_t err_code){
  while(1);
}
#endif

int main(int argc, const char*argv[]){
  const char*info[] = {
    "version", xstr(GIT_VERSION)
  };
  init(argc,argv);
  #if 0==RAW_COM
  LBMK_init_leancom();
  #endif
  LBMK_rng_init();
  sum_custom_benchmark(10);
  #ifdef RUN_ONCE
  bool run_forever=0;
  #else
  bool run_forever=1;
  #endif
  do{
    LBMK_announce_start(2,info);
    LBMK_benchmarkit(&sum_benchmark_simple_setup,0);
    LBMK_benchmarkit(&sum_benchmark_setup_with_extra_data,0);
    LBMK_announce_end();
  }while(run_forever);
  delay_ms(1000);//give some time to receiver before cutting connection
  return 0;
}


