#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
#include "util.h"
#define LBMK_NO_PRINT_DECL
#include "lean-benchmark.h"

#define PRINT_PREFIX LBMK_
void LBMK_print_impl(const char*msg){
  unsigned int len = strlen(msg);
  LBMK_com_tx(msg,len);
}
#define PRINT_FUNC_DECL
#include "print.h"

const char*LBMK_version = xstr(GIT_VERSION);

volatile uint64_t io_sink;
//'touch' pointers to avoid optimization on the caller site (assuming it is called outside of this lib)
//don't use LTO with this one
void __attribute__((noinline)) LBMK_touch_pointers(int n, ...){
  va_list args;
  va_start(args, n);  
  for (int i = 0; i < n; i++) {
    io_sink ^= va_arg(args,uintptr_t);//not really needed, it is note safe against LTO, we would need to access all the data...
  }
  va_end(args);
}

uint64_t __attribute__((noinline)) donothing(uintptr_t*a){return (uint32_t)(uintptr_t)a;}

void LBMK_write_io(uint64_t data){
  io_sink ^= data;
}
volatile uint8_t io_source=0;
volatile uint64_t io_source64=0;
void LBMK_memcpy_io(void*dst, const void*src, unsigned int size){
  uint8_t*dst8 = (uint8_t*)dst;
  const uint8_t*src8 = (const uint8_t*)src;
  for(unsigned int i=0;i<size;i++){
    dst8[i] = src8[i] ^ io_source;
  }
}
void LBMK_memset_io(void*dst, uint8_t val, unsigned int size){
  uint8_t*dst8 = (uint8_t*)dst;
  for(unsigned int i=0;i<size;i++){
    dst8[i] = val ^ io_source;
  }
}
uint32_t __attribute__((noinline)) ret0(void*a){return 0;}
#define STACK_MEASUREMENT_VAL 0x66

void __attribute__((noinline)) LBMK_init_stack(uint32_t max_size){
  uint8_t stack[max_size];
  LBMK_memset_io(stack,STACK_MEASUREMENT_VAL,max_size);
}

uintptr_t __attribute__((noinline)) LBMK_measure_stack_size(uint32_t max_size){
  uint8_t stack_top;
  uint8_t*stack = &stack_top+1;
  stack -= max_size;
  while(STACK_MEASUREMENT_VAL==*stack){
    stack++;
  }
  uintptr_t size = &stack_top - stack + 1;
  return size;
}

static volatile bool within_benchmarked_func = 0;
bool __attribute__((noinline)) LBMK_is_within_benchmarked_func(){
  return within_benchmarked_func;
}

uint64_t __attribute__((noinline)) LBMK_timeit(uint64_t (*dut)(uintptr_t*), void*args, uint32_t*cycles){
  LBMK_init_heap_usage();
  within_benchmarked_func = 1;
  const uint64_t start = LBMK_get_cpu_timestamp();
  const uint64_t out = dut(args);
  const uint64_t end = LBMK_get_cpu_timestamp();
  within_benchmarked_func = 0;
  *cycles = end-start;
  return out;
}

uint64_t LBMK_benchmarkit_core(uint64_t (*dut)(uintptr_t*), uintptr_t*args,  unsigned int size, unsigned int max_stack_size, benchmark_result_t*result){
  uintptr_t safe_args[size / sizeof(uintptr_t)];
  uint64_t (*funcs[2])(uintptr_t*) = {donothing, dut};
  uint32_t cycles[2];
  uint64_t out = 0;
  LBMK_memcpy_io(safe_args, args, size); // prevent build time optimizations
  LBMK_init_stack(max_stack_size);
  for(unsigned int i=0;i<2;i++){
    out = LBMK_timeit(funcs[i],safe_args,cycles+i);
  }
  const uint32_t stack_size = LBMK_measure_stack_size(max_stack_size);
  uint64_t safe_out;
  LBMK_memcpy_io(&safe_out, &out, sizeof(safe_out)); // prevent build time optimizations
  result->cycles = cycles[1]-cycles[0];
  result->stack_size = stack_size;
  return safe_out;
}

static void write_u32(uint32_t u){
  LBMK_com_tx(&u,sizeof(u));
}

static void write_u64(uint64_t u){
  LBMK_com_tx(&u,sizeof(u));
}

static void write_string(const char*s){
  uint32_t size = strlen(s);
  write_u32(size);
  LBMK_com_tx(s,size);
}

void LBMK_announce_start(unsigned int ninfo, const char*info[]){
  write_string("\nlean-benchmark start\n");
  write_u32(ninfo);
  for(unsigned int i=0;i<ninfo;i++){
    write_string(info[i]);
  }
}
void LBMK_announce_end(){
  write_u32(0);
}
void LBMK_benchmarkit(benchmark_setup_t*setup, unsigned int case_index){
  write_string(setup->dut_name);
  write_string(setup->args_setup_name);
  write_u32(setup->nargs);
  write_u32(setup->ntrials);
  write_u32(setup->max_stack_size);
  write_u32(setup->nextra_data);
  write_u32(case_index);
  for(unsigned int i=0;i<setup->ntrials;i++){
    benchmark_result_t result;
    uintptr_t args[setup->nargs];
    tlv_t extra_data_info[setup->nextra_data+1];
    if(setup->args_setup) setup->args_setup(args);
    uint64_t output = LBMK_benchmarkit_core(setup->dut,args,sizeof(args),setup->max_stack_size,&result);
    if(setup->post_exec) setup->post_exec(extra_data_info, args, output);
    write_u32(result.cycles);
    write_u32(result.stack_size);
    const uint64_t heap_usage = LBMK_get_heap_usage();
    write_u64(heap_usage);
    for(unsigned int j=0;j<setup->nextra_data;j++){
      write_string(extra_data_info[j].tag);
      write_u32(extra_data_info[j].length);
      LBMK_com_tx(extra_data_info[j].value, extra_data_info[j].length);
    }
  }
}

static uint64_t rng64;

void __attribute__((weak)) LBMK_rng_init(){
  rng64 = 0xFFFFFFFFFFFFFFFF;
}

void __attribute__((weak)) LBMK_rng_inject_entropy(uint32_t rnd){
  rng64 ^= rnd;
  if(0==rng64) rng64 = 0xFFFFFFFFFFFFFFFF;
  LBMK_rng_get64();
}

unsigned int __attribute__((weak)) LBMK_rng_get_state_size(){
  return sizeof(rng64) ;
}

void __attribute__((weak)) LBMK_rng_get_state(void*dst){
  memcpy(dst,&rng64,sizeof(rng64));
}

void __attribute__((weak)) LBMK_rng_set_state(const void*src){
  memcpy(&rng64,src,sizeof(rng64));
}


__attribute__((weak)) uint64_t LBMK_rng_get64(){
  // Algorithm "xor" from p. 4 of Marsaglia, "Xorshift RNGs"
  uint64_t x = rng64;
  x ^= x << 13; 
  x ^= x >> 7; 
  x ^= x << 17;
  return rng64 = x;
}

__attribute__((weak)) void LBMK_rng_fill64(uint64_t*dst, unsigned int n_words){
  for(unsigned int i=0;i<n_words;i++){
    dst[i] = LBMK_rng_get64();
  }
}

__attribute__((weak)) void LBMK_rng_fill(uint8_t*dst, unsigned int size){
  for(unsigned int i=0;i<size;i++){
    dst[i] = LBMK_rng_get64();
  }
}

