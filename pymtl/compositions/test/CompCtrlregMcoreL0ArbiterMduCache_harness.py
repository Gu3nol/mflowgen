#=========================================================================
# test_harness
#=========================================================================
# Includes a test harness that composes a processor, src/sink, and test
# memory, and a run_test function.

import struct

from pymtl import *

from pclib.test import TestSource, TestSink
from proc.SparseMemoryImage import SparseMemoryImage

# BRGTC2 custom TestMemory modified for RISC-V 32

from test import TestMemory

# BRGTC2 custom MemMsg modified for RISC-V 32

from ifcs import MemMsg, MduMsg, CtrlRegMsg,CtrlRegReqMsg, CtrlRegRespMsg

#=========================================================================
# TestHarness
#=========================================================================
# Use this with pytest parameterize so that the name of the function that
# generates the assembly test ends up as part of the actual test case
# name. Here is an example:
#
#  @pytest.mark.parametrize( "name,gen_test", [
#    asm_test( gen_basic_test  ),
#    asm_test( gen_bypass_test ),
#    asm_test( gen_value_test  ),
#  ])
#  def test( name, gen_test ):
#    run_test( ProcXFL, gen_test )
#

def asm_test( func ):
  name = func.__name__
  if name.startswith("gen_"):
    name = name[4:]
  if name.endswith("_test"):
    name = name[:-5]

  return (name,func)

#=========================================================================
# TestHarness
#=========================================================================

class TestHarness( Model ):

  #-----------------------------------------------------------------------
  # constructor
  #-----------------------------------------------------------------------

  def __init__( s, model, dump_vcd, test_verilog, num_cores, cacheline_nbits,
                src_delay, sink_delay, mem_stall_prob, mem_latency ):

    num_memports = 2   # 1 dmem, 1 imem
    s.num_cores  = num_cores

    # 10 bundles are going out from the composition
    # - 1 x ctrlreg req/resp
    # - 4 x mngrproc/proc2mngr
    # - 1 x host_mdu    req/resp
    # - 1 x host_icache req/resp
    # - 1 x host_dcache req/resp
    # - 1 x actual imem req/resp
    # - 1 x actual dmem req/resp

    # Interface types
    mopaque_nbits = 8
    addr_nbits    = 32
    word_nbits    = 32

    s.ctrlregifc     = CtrlRegMsg()
    s.proc_cache_ifc = MemMsg( mopaque_nbits, addr_nbits, word_nbits )
    s.cache_mem_ifc  = MemMsg( mopaque_nbits, addr_nbits, cacheline_nbits )
    s.proc_mdu_ifc   = MduMsg( 32, 8 )

    s.ctrlregsrc  = TestSource ( s.ctrlregifc.req , [], src_delay  )
    s.ctrlregsink = TestSink   ( s.ctrlregifc.resp, [], sink_delay )

    s.src         = TestSource[num_cores]( 32, [], src_delay  )
    s.sink        = TestSink  [num_cores]( 32, [], sink_delay )

    s.host_mdu_src     = TestSource( s.proc_mdu_ifc.req , [], src_delay  )
    s.host_mdu_sink    = TestSink  ( s.proc_mdu_ifc.resp, [], sink_delay )

    s.host_icache_src  = TestSource( s.cache_mem_ifc.req , [], src_delay  )
    s.host_icache_sink = TestSink  ( s.cache_mem_ifc.resp, [], sink_delay )

    s.host_dcache_src  = TestSource( s.proc_cache_ifc.req , [], src_delay  )
    s.host_dcache_sink = TestSink  ( s.proc_cache_ifc.resp, [], sink_delay )

    s.mem = TestMemory( MemMsg(8,32,cacheline_nbits),
                        num_memports, mem_stall_prob, mem_latency )

    # model

    s.model = model

    # Dump VCD

    if dump_vcd:
      s.model.vcd_file = dump_vcd

    if test_verilog:
      cls_name = s.model.__class__.__name__
      if ( cls_name != 'SwShim' ) and ( not hasattr( s.model, 'dut' ) ):
        s.model = TranslationTool( s.model, enable_blackbox = True, verilator_xinit=test_verilog )

    # Ctrlreg

    s.connect( s.model.ctrlregreq,  s.ctrlregsrc.out   )
    s.connect( s.model.ctrlregresp, s.ctrlregsink.in_  )

    # Composition <-> Memory

    s.connect( s.model.imemreq,  s.mem.reqs[0]     )
    s.connect( s.model.imemresp, s.mem.resps[0]    )
    s.connect( s.model.dmemreq,  s.mem.reqs[1]     )
    s.connect( s.model.dmemresp, s.mem.resps[1]    )

    # Processor <-> Proc/Mngr

#    for i in xrange(num_cores):
#      s.connect( s.model.mngr2proc[i], s.src[i].out  )
#      s.connect( s.model.proc2mngr[i], s.sink[i].in_ )

    s.connect( s.model.mngr2proc_0, s.src [0].out  )
    s.connect( s.model.proc2mngr_0, s.sink[0].in_ )
    s.connect( s.model.mngr2proc_1, s.src [1].out  )
    s.connect( s.model.proc2mngr_1, s.sink[1].in_ )
    s.connect( s.model.mngr2proc_2, s.src [2].out  )
    s.connect( s.model.proc2mngr_2, s.sink[2].in_ )
    s.connect( s.model.mngr2proc_3, s.src [3].out  )
    s.connect( s.model.proc2mngr_3, s.sink[3].in_ )

    s.connect_pairs(
      s.model.host_mdureq,  s.host_mdu_src.out,
      s.model.host_mduresp, s.host_mdu_sink.in_,

      s.model.host_icachereq,  s.host_icache_src.out,
      s.model.host_icacheresp, s.host_icache_sink.in_,

      s.model.host_dcachereq,  s.host_dcache_src.out,
      s.model.host_dcacheresp, s.host_dcache_sink.in_,
    )

  #-----------------------------------------------------------------------
  # load_ctrlreg
  #-----------------------------------------------------------------------
  # This function loads messages into s.ctrlregsrc/s.ctrlregsink

  def load_ctrlreg( self ):

    def req_cr( type_, addr, data ):
      msg       = CtrlRegReqMsg()
      msg.type_ = type_
      msg.addr  = addr
      msg.data  = data
      return msg

    def resp_cr( type_, data ):
      msg       = CtrlRegRespMsg()
      msg.type_ = type_
      msg.data  = data
      return msg

    rd = CtrlRegReqMsg.TYPE_READ
    wr = CtrlRegReqMsg.TYPE_WRITE

    #                Req   Req   Req              Resp  Resp
    #                Type  Addr  Data             Type  Data
    msgs = [ req_cr(   rd,    1,    0 ), resp_cr(   rd,    0 ), # read debug
             req_cr(   wr,    1,    1 ), resp_cr(   wr,    0 ), # write debug
             req_cr(   rd,    1,    0 ), resp_cr(   rd,    1 ), # read debug
             req_cr(   wr,    0,    1 ), resp_cr(   wr,    0 ), # go
           ]

    self.ctrlregsrc.src.msgs   = msgs[::2]
    self.ctrlregsink.sink.msgs = msgs[1::2]

  #-----------------------------------------------------------------------
  # load_asm
  #-----------------------------------------------------------------------
  # This function loads messages into s.src0-3, s.sink0-3 and memory data

  def load_asm( self, mem_image ):

    # Iterate over the sections

    sections = mem_image.get_sections()
    for section in sections:

      # For .mngr2proc sections, copy section into mngr2proc src

      if section.name == ".mngr2proc":
        for i in xrange(0,len(section.data),4):
          bits = struct.unpack_from("<I",buffer(section.data,i,4))[0]
          for i in xrange(self.num_cores):
            self.src[i].src.msgs.append( Bits(32,bits) )

      elif section.name.endswith("_2proc"):
        idx = int( section.name[5:-6], 0 )

        for i in xrange(0,len(section.data),4):
          bits = struct.unpack_from("<I",buffer(section.data,i,4))[0]
          self.src[idx].src.msgs.append( Bits(32,bits) )

      # For .proc2mngr sections, copy section into proc2mngr_ref src

      elif section.name == ".proc2mngr":
        for i in xrange(0,len(section.data),4):
          bits = struct.unpack_from("<I",buffer(section.data,i,4))[0]

          for i in xrange(self.num_cores):
            self.sink[i].sink.msgs.append( Bits(32,bits) )

      elif section.name.endswith("_2mngr"):
        idx = int( section.name[5:-6], 0 )

        for i in xrange(0,len(section.data),4):
          bits = struct.unpack_from("<I",buffer(section.data,i,4))[0]
          self.sink[idx].sink.msgs.append( Bits(32,bits) )

      # For all other sections, simply copy them into the memory

      else:
        start_addr = section.addr
        stop_addr  = section.addr + len(section.data)
        self.mem.mem[start_addr:stop_addr] = section.data

  #-----------------------------------------------------------------------
  # load_mdu
  #-----------------------------------------------------------------------
  # This function loads messages into s.host_mdu_src/s.host_mdu_sink

  def load_mdu( self, msgs ):
    self.host_mdu_src.src.msgs   = msgs[::2]
    self.host_mdu_sink.sink.msgs = msgs[1::2]

  #-----------------------------------------------------------------------
  # load_icache
  #-----------------------------------------------------------------------
  # This function loads messages into s.host_icache_src/s.host_icache_sink

  def load_icache( self, msgs ):
    self.host_icache_src.src.msgs   = msgs[::2]
    self.host_icache_sink.sink.msgs = msgs[1::2]

  #-----------------------------------------------------------------------
  # load_dcache
  #-----------------------------------------------------------------------
  # This function loads messages into s.host_dcache_src/s.host_dcache_sink

  def load_dcache( self, msgs ):
    self.host_dcache_src.src.msgs   = msgs[::2]
    self.host_dcache_sink.sink.msgs = msgs[1::2]

  #-----------------------------------------------------------------------
  # cleanup
  #-----------------------------------------------------------------------

  def cleanup( s ):
    del s.mem.mem[:]

  #-----------------------------------------------------------------------
  # done
  #-----------------------------------------------------------------------

  def done( s ):
    return s.ctrlregsrc.done and s.ctrlregsink.done and \
          reduce( lambda x,y : x and y, [x.done for x in s.src]+[x.done for x in s.sink] ) and \
          s.host_mdu_src.done and s.host_mdu_sink.done and \
          s.host_icache_src.done and s.host_icache_sink.done and \
          s.host_dcache_src.done and s.host_dcache_sink.done

  #-----------------------------------------------------------------------
  # line_trace
  #-----------------------------------------------------------------------

  def line_trace( s ):
    #s.model.ctrlreg.line_trace() + " > " + \
    return s.ctrlregsrc.line_trace()  + " > " + \
           s.ctrlregsink.line_trace() + \
           "|".join( [x.line_trace() for x in s.src]  ) + \
           s.model.line_trace() + \
           "|".join( [x.line_trace() for x in s.sink] )

#=========================================================================
# run_test
#=========================================================================

def run_test( model, msgs, num_cores, cacheline_nbits=128,
              dump_vcd=None, test_verilog=False, src_delay=0, sink_delay=0,
              mem_stall_prob=0, mem_latency=0, max_cycles=200000 ):

  assert isinstance( msgs, list )
  assert len(msgs) == 5

  # Instantiate and elaborate the model

  model = TestHarness( model, dump_vcd, test_verilog, num_cores, cacheline_nbits,
                       src_delay, sink_delay, mem_stall_prob, mem_latency )

  model.vcd_file = dump_vcd
  model.elaborate()

  # five messages

  assert isinstance( msgs[0], bool ) # ctrlreg
  assert isinstance( msgs[1], SparseMemoryImage ) or msgs[1] is None # asm test
  assert isinstance( msgs[2], list ) # mdu
  assert isinstance( msgs[3], list ) # icache
  assert isinstance( msgs[4], list ) # dcache

  if msgs[0] == True:
    model.load_ctrlreg()

  if msgs[1]:
    model.load_asm( msgs[1] )

  if msgs[2]:
    model.load_mdu( msgs[2] )

  if msgs[3]:
    model.load_icache( msgs[3] )

  if msgs[4]:
    model.load_dcache( msgs[4] )

  # Create a simulator using the simulation tool

  sim = SimulationTool( model )

  # Run the simulation

  print()

  sim.reset()
  while not model.done() and sim.ncycles < max_cycles:
    sim.print_line_trace()
    sim.cycle()

  # print the very last line trace after the last tick

  sim.print_line_trace()

  # Force a test failure if we timed out

  assert sim.ncycles < max_cycles

  # Add a couple extra ticks so that the VCD dump is nicer

  sim.cycle()
  sim.cycle()
  sim.cycle()

  model.cleanup()