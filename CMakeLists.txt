cmake_minimum_required(VERSION 3.22)

project(lean-benchmark-test-fw LANGUAGES C ASM)

#message(WARNING "CMAKE_C_COMPILER is ${CMAKE_C_COMPILER}")
#message(WARNING "CMAKE_AR is ${CMAKE_AR}")

if(NOT DEFINED RAW_COM)
set(RAW_COM 0)
ENDIF()
MESSAGE("RAW_COM=" ${RAW_COM})
ADD_DEFINITIONS(-DRAW_COM=${RAW_COM})


set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS ON)

add_subdirectory(liblean-benchmark)

if(BUILD_TEST)

# Sources
set(sources_SRCS
	${CMAKE_CURRENT_SOURCE_DIR}/test/source/main.c
)

# Include directories
set(include_c_DIRS
	${CMAKE_CURRENT_SOURCE_DIR}/test/include
	${CMAKE_CURRENT_SOURCE_DIR}/liblean-benchmark/include
)

# libs
set(link_DIRS
	${CMAKE_CURRENT_BINARY_DIR}/lean-benchmark
)

list(APPEND link_LIBS lean-benchmark)

include("cmake/generic_binary.cmake")

include(CTest)
add_test(NAME lean-benchmark-test-fw
					COMMAND lean-benchmark-test-fw)

endif(BUILD_TEST)