cmake_minimum_required(VERSION 3.13)
if (DEFINED ENV{PICO_SDK_PATH} AND (NOT PICO_SDK_PATH))
    set(PICO_SDK_PATH $ENV{PICO_SDK_PATH} CACHE PATH "Path to the Pico SDK")
endif()
include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(roamer_pico C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(roamer_pico
    main.c
    motor.c
    encoder.c
    sensors.c
)

target_link_libraries(roamer_pico
    pico_stdlib
    hardware_pwm
    hardware_adc
    hardware_gpio
)

# USB CDC serial for the Pico<->Pi protocol (ttyACM0 on the Pi)
pico_enable_stdio_usb(roamer_pico 1)
pico_enable_stdio_uart(roamer_pico 0)

pico_add_extra_outputs(roamer_pico)
