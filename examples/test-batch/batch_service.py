import os
import sys
import math
from time import time
from typing import Optional
from pydantic import BaseModel, Field
from ivcap_fastapi import getLogger, logging_init

this_dir = os.path.dirname(__file__)
src_dir = os.path.abspath(os.path.join(this_dir, "../../src"))
sys.path.insert(0, src_dir)

logging_init()
logger = getLogger("app")

TITLE="Batch service to test various platform aspects"

class Request(BaseModel):
    jschema: str = Field("urn:sd:schema:batch-tester.request.1", alias="$schema")
    duration_seconds: Optional[int] = Field(10, description="seconds this job should run")
    target_cpu_percent: Optional[int] = Field(80, description="percentage load on CPU")

class Result(BaseModel):
    jschema: str = Field("urn:sd:schema:batch-tester.1", alias="$schema")
    msg: str = Field(None, description="some message")
    run_time: float = Field(description="time in seconds this job took")

import time
import math

def consume_compute(req: Request) -> Result:
    """
    Consumes a significant amount of CPU for a specified duration, useful for testing.

    This function attempts to consume a target percentage of CPU by performing
    mathematical operations in a loop.  It's single-threaded, so its
    effectiveness in consuming a specific percentage of *total* CPU will
    depend on the number of CPU cores available.  For example, on a
    quad-core machine, this function targeting 80% will consume roughly
    80% of one core's capacity, or 20% of the total CPU.

    Args:
        duration_seconds: The number of seconds to consume CPU.
        target_cpu_percent: The target CPU utilization as a percentage (0-100).
            Note that achieving a precise percentage is difficult due to
            Python's overhead and the nature of CPU scheduling.
    """
    duration_seconds = req.duration_seconds
    target_cpu_percent = req.target_cpu_percent

    if not 0 <= target_cpu_percent <= 100:
        raise ValueError("target_cpu_percent must be between 0 and 100")

    start_time = time.time()
    end_time = start_time + duration_seconds
    logger.debug(f"Consuming CPU for {duration_seconds} seconds, targeting {target_cpu_percent}% per core...")

    # Constants to control the workload.  These may need adjustment.
    base_iterations = 10000  # A starting point for the loop iterations.
    load_factor = target_cpu_percent / 100.0  # Convert percentage to a fraction.

    loop_count = 0
    while time.time() < end_time:
        # Adjust the number of iterations to try to hit the target CPU.
        iterations = int(base_iterations * load_factor)

        # A simple loop with some math operations to consume CPU.
        for i in range(iterations):
            x = math.sqrt(i * 1.234)
            y = math.log(x + 1)
            z = math.pow(y, 2.345)
            w = math.sin(z)

        # A small sleep to prevent the loop from running *too* fast and
        # potentially starving other processes or causing issues.  The
        # optimal sleep time may vary by system.  If target_cpu_percent
        # is very high (e.g., > 90), this might need to be reduced or
        # eliminated.
        time.sleep(0.001)
        loop_count += 1

    run_time = time.time() - start_time
    logger.info(f"CPU consumption finished after {run_time} sec (loops: {loop_count})")
    return Result(msg="CPU consumption finished.", run_time=run_time)

# add_tool_api_route(app, "/", tester, opts=ToolOptions(tags=["Test Tool"], service_id="/"), context=ExecCtxt(msg="Boo!"))
# add_tool_api_route(app, "/async", async_tester, opts=ToolOptions(tags=["Test Tool"]))

if __name__ == "__main__":
    from server import start_service
    start_service(TITLE, consume_compute)
