#!/bin/bash

echo "exec python"
time for ((x=0;x<100;x=x+1)) do python ./test_small_cpu_task.py > /dev/null 2>&1 ; done

echo "exec pyzy_client"
time for ((x=0;x<100;x=x+1)) do ../pyzy_client ./test_small_cpu_task.py > /dev/null 2>&1 ; done
