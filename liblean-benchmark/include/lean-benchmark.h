#pragma once

#include <stdint.h>
#include <stdbool.h>

//functions that must be provided by the environment
void LBMK_com_tx(const void*data, unsigned int size);
uint64_t LBMK_get_cpu_timestamp();
void LBMK_init_heap_usage();
uint64_t LBMK_get_heap_usage();//you can call LBMK_is_within_benchmarked_func to know if an allocation is done by the benchmarked function or not
void LBMK_clear_caches();

typedef struct {
  const char*tag;
  uint32_t length;
  uint8_t*value;
} tlv_t;

//top level function
typedef struct {
  char*dut_name;
  char*args_setup_name;
  uint64_t (*dut)(uintptr_t*);
  void (*args_setup)(uintptr_t*);
  unsigned int nargs;
  unsigned int ntrials;
  unsigned int max_stack_size; 
  void (*post_exec)(tlv_t*, uintptr_t*,uint64_t);
  unsigned int nextra_data;
  unsigned int extra_data_size;
} benchmark_setup_t;

void LBMK_init_leancom();//optional, if you use it, it must be the first LBMK_* function to be called
int LBMK_putchar(int c);//optional, if you want to use printf, use this to override putchar function
void LBMK_announce_start(unsigned int ninfo, const char*info[]);
void LBMK_benchmarkit(benchmark_setup_t*setup, unsigned int case_index);
void LBMK_announce_end();

//helper functions if the main function cannot be used
typedef struct {
  uint32_t cycles;
  uint32_t stack_size;
} benchmark_result_t;

uint64_t LBMK_benchmarkit_core(uint64_t (*dut)(uintptr_t*), uintptr_t*args,  unsigned int size, unsigned int max_stack_size, benchmark_result_t*result);
void LBMK_write_io(uint64_t data);
void LBMK_memcpy_io(void*dst, const void*src, unsigned int size);
void LBMK_memset_io(void*dst, uint8_t val, unsigned int size);
void LBMK_init_stack(uint32_t max_size);
uintptr_t LBMK_measure_stack_size(uint32_t max_size);
uint64_t LBMK_timeit(uint64_t (*dut)(uintptr_t*), void*args, uint32_t*cycles);
bool LBMK_is_within_benchmarked_func();

//additional helper functions
void LBMK_rng_init();
void LBMK_rng_inject_entropy(uint32_t rnd);
unsigned int LBMK_rng_get_state_size();
void LBMK_rng_get_state(void*dst);
void LBMK_rng_set_state(const void*src);
uint64_t LBMK_rng_get64();
void LBMK_rng_fill(uint8_t*dst, unsigned int size);
void LBMK_touch_pointers(int n, ...);

#ifndef LBMK_NO_PRINT_DECL
void LBMK_print_uint_as_hex(uint64_t num, unsigned int nhexdigits);
void LBMK_print_uint_as_dec(uint64_t num, unsigned int ndecdigits);
void LBMK_println(const char*msg);
void LBMK_print8x(const char*msg1,uint8_t val,const char*msg2);
void LBMK_println8x(const char*msg1,uint8_t val);
void LBMK_print8d(const char*msg1,uint32_t val,const char*msg2);
void LBMK_println8d(const char*msg1,uint32_t val);
void LBMK_print16x(const char*msg1,uint16_t val,const char*msg2);
void LBMK_println16x(const char*msg1,uint16_t val);
void LBMK_print16d(const char*msg1,uint32_t val,const char*msg2);
void LBMK_println16d(const char*msg1,uint32_t val);
void LBMK_print32x(const char*msg1,uint32_t val,const char*msg2);
void LBMK_println32x(const char*msg1,uint32_t val);
void LBMK_print32d(const char*msg1,uint32_t val,const char*msg2);
void LBMK_println32d(const char*msg1,uint32_t val);
void LBMK_print64x(const char*msg1,uint64_t val,const char*msg2);
void LBMK_println64x(const char*msg1,uint64_t val);
void LBMK_print64d(const char*msg1,uint32_t val,const char*msg2);
void LBMK_println64d(const char*msg1,uint32_t val);
void LBMK_print_bytes_sep(const char*msg1,const void*const buf,unsigned int size, const char*msg2, const char*const separator);
void LBMK_print_bytes(const char*msg1,const void*const buf,unsigned int size, const char*msg2);
void LBMK_println_bytes(const char*msg1,const void*const buf,unsigned int size);
void LBMK_print_bytes_0x(const char*msg1,const void*const buf,unsigned int size, const char*msg2);
void LBMK_println_bytes_0x(const char*msg1,const void*const buf,unsigned int size);
void LBMK_print_array32x_0xln(const void*const buf, unsigned int n_elements);
void LBMK_printuix(const char*msg1,unsigned int val,const char*msg2);
void LBMK_printlnuix(const char*msg1,unsigned int val);
void LBMK_printulx(const char*msg1,unsigned long val,const char*msg2);
void LBMK_printlnulx(const char*msg1,unsigned long val);
#endif
