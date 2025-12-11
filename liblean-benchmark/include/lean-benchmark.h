#pragma once

#include <stdint.h>

//functions that must be provided by the environment
void LBMK_com_tx(const void*data, unsigned int size);
uint64_t LBMK_get_cpu_timestamp();

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

//additional helper functions
void LBMK_rng_init();
void LBMK_rng_inject_entropy(uint32_t rnd);
unsigned int LBMK_rng_get_state_size();
void LBMK_rng_get_state(void*dst);
void LBMK_rng_set_state(const void*src);
uint64_t LBMK_rng_get64();
void LBMK_rng_fill(uint8_t*dst, unsigned int size);

