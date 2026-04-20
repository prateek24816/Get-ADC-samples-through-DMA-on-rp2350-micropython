# Get-ADC-samples-through-DMA-on-rp2350-micropython
micropython library to use DMA for ADC sampling on raspberry pi pico 2

You can set the sample size and the sample frequency (max is 500KSPS, after that the pico just goes to free mode taking samples as fast as it can which is more than 50x-100x what you can get using a while loop and adc.read_u16() in micropython).
The size of a single sample is 2 bytes and the actual true ADC output is stored (12 bits) unlike the scaled micropython version.
