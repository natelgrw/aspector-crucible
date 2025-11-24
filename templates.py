SINGLE_ENDED_TEMPLATE = """simulator lang=spectre 
global 0 gnd! vdd!
parameters fet_num=<<FET_NUM>> use_tran=0 rfeedback_val=1000 dc_offset=0 gain_n=-0.5 tempc={{tempc}} vdd={{vdd}} vcm={{vcm}} vbiasp2={{vbiasp2}} vbiasn0={{vbiasn0}} vbiasn2={{vbiasn2}} <<EXTRA_PARAMS>>

<<INCLUDES>>

*---Core---
<<CORE_NETLIST>>

*---Ground, VDD, VCM Declarations---
VS (gnd! 0) vsource dc=0 type=dc
V0 (vdd! gnd!) vsource dc=vdd type=dc
V1 (cm gnd!) vsource dc=vcm type=dc

*---Voltage Input---
V2 (in gnd!) vsource dc=dc_offset type=dc mag=1
E1 (Vinp_norm cm in gnd!) vcvs gain=0.5
E0 (Vinn_norm cm in gnd!) vcvs gain=gain_n

*---Transient Input---
Vstep (in_tran gnd!) vsource type=pulse val0=(0.1 * vdd) val1=(0.9 * vdd) delay=1n rise=50p fall=50p width=100n period=200n
E3 (Vinp_tran cm in_tran gnd!) vcvs gain=0.5
E2 (Vinn_tran cm in_tran gnd!) vcvs gain=-0.5

*--- Switchable Inputs to Core ---
Rin1 (Vinp Vinp_norm) resistor r=(1 / (1 - use_tran + 1p))
Rin2 (Vinp Vinp_tran) resistor r=(1 / (use_tran + 1p))

Rin3 (Vinn Vinn_norm) resistor r=(1 / (1 - use_tran + 1p))
Rin4 (Vinn Vinn_tran) resistor r=(1 / (use_tran + 1p))

Rfeedback_p (Vinn Voutp) resistor r=((use_tran * rfeedback_val) + ((1 - use_tran) * 1T))

Ctran_p (Voutp gnd!) capacitor c=(use_tran * 50f)

*---Bias Voltages---
VP2 (Vbiasp2 gnd!) vsource dc=vbiasp2 type=dc
VN (Vbiasn0 gnd!) vsource dc=vbiasn0 type=dc
VN2 (Vbiasn2 gnd!) vsource dc=vbiasn2 type=dc

simulatorOptions options rawfmt=psfbin psfversion="1.4.0" reltol=1e-3 vabstol=1e-6 \\
    iabstol=1e-12 temp=tempc tnom=27 scalem=1.0 scale=1.0 gmin=1e-12 rforce=1 \\
    maxnotes=5 maxwarns=5 digits=5 cols=80 pivrel=1e-3 \\
    sensfile="../psf/sens.output" checklimitdest=psf 

*---Noise Simulation---
noise (Voutp 0) noise start=1M stop=500M dec=20 iprobe=V2 annotate=status

*---AC Sweep---
acswp sweep param=gain_n start=-0.5 stop=0.5 step=1 {
    ac ac start=1 stop=100G dec=10 annotate=status
}

*---DC Sweep---
dcswp sweep param=dc_offset start=-0.5 stop=0.5 step=0.001 {
    dcOp dc write="spectre.dc" maxiters=150 maxsteps=10000 annotate=status
}

*---Transient Sweep---
transwp sweep param=use_tran values=[1] {
    mytran tran stop=200n step=5p annotate=status
}

dcOpInfo info what=oppoint where=rawfile
modelParameter info what=models where=rawfile
element info what=inst where=rawfile
outputParameter info what=output where=rawfile
designParamVals info what=parameters where=rawfile
primitives info what=primitives where=rawfile
subckts info what=subckts where=rawfile

saveOptions options save=allpub rawfmt=psfbin
"""

DIFFERENTIAL_TEMPLATE = """simulator lang=spectre 
global 0 gnd! vdd!
parameters use_tran=0 rfeedback_val=1000 dc_offset=0 gain_n=-0.5 tempc={{tempc}} vdd={{vdd}} vcm={{vcm}} vbiasp0={{vbiasp0}} vbiasp1={{vbiasp1}} vbiasp2={{vbiasp2}} vbiasn1={{vbiasn1}} vbiasn2={{vbiasn2}} <<EXTRA_PARAMS>>

<<INCLUDES>>

*---Core---
<<CORE_NETLIST>>

*---Ground, VDD, VCM Declarations---
VS (gnd! 0) vsource dc=0 type=dc
V0 (vdd! gnd!) vsource dc=vdd type=dc
V1 (cm gnd!) vsource dc=vcm type=dc

*---Voltage Input---
V2 (in gnd!) vsource dc=dc_offset type=dc mag=1
E1 (Vinp_norm cm in gnd!) vcvs gain=0.5
E0 (Vinn_norm cm in gnd!) vcvs gain=gain_n

*---Transient Input---
Vstep (in_tran gnd!) vsource type=pulse val0=(0.1 * vdd) val1=(0.9 * vdd) delay=1n rise=50p fall=50p width=100n period=200n
E3 (Vinp_tran cm in_tran gnd!) vcvs gain=0.5
E2 (Vinn_tran cm in_tran gnd!) vcvs gain=-0.5

*--- Switchable Inputs to Core ---
Rin1 (Vinp Vinp_norm) resistor r=(1 / (1 - use_tran + 1p))
Rin2 (Vinp Vinp_tran) resistor r=(1 / (use_tran + 1p))

Rin3 (Vinn Vinn_norm) resistor r=(1 / (1 - use_tran + 1p))
Rin4 (Vinn Vinn_tran) resistor r=(1 / (use_tran + 1p))

Rfeedback_p (Vinn Voutp) resistor r=((use_tran * rfeedback_val) + ((1 - use_tran) * 1T))
Rfeedback_n (Vinp Voutn) resistor r=((use_tran * rfeedback_val) + ((1 - use_tran) * 1T))

Ctran_p (Voutp gnd!) capacitor c=(use_tran * 50f)
Ctran_n (Voutn gnd!) capacitor c=(use_tran * 50f)

*---Bias Voltages---
VP (Vbiasp0 gnd!) vsource dc=vbiasp0 type=dc
VP1 (Vbiasp1 gnd!) vsource dc=vbiasp1 type=dc
VP2 (Vbiasp2 gnd!) vsource dc=vbiasp2 type=dc
VN1 (Vbiasn1 gnd!) vsource dc=vbiasn1 type=dc
VN2 (Vbiasn2 gnd!) vsource dc=vbiasn2 type=dc

simulatorOptions options psfversion="1.4.0" reltol=1e-3 vabstol=1e-6 \\
    iabstol=1e-12 temp=tempc tnom=27 scalem=1.0 scale=1.0 gmin=1e-12 rforce=1 \\
    maxnotes=5 maxwarns=5 digits=5 cols=80 pivrel=1e-3 \\
    sensfile="../psf/sens.output" checklimitdest=psf 

*---Noise Simulation---
noise (Voutp 0) noise start=1M stop=500M dec=20 iprobe=V2 annotate=status

*---AC Sweep---
acswp sweep param=gain_n start=-0.5 stop=0.5 step=1 {
    ac ac start=1 stop=100G dec=10 annotate=status
}

*---DC Sweep---
dcswp sweep param=dc_offset start=-0.5 stop=0.5 step=0.001 {
    dcOp dc write="spectre.dc" maxiters=150 maxsteps=10000 annotate=status
}

*---Transient Sweep---
transwp sweep param=use_tran values=[1] {
    mytran tran stop=200n step=5p annotate=status
}

dcOpInfo info what=oppoint where=rawfile
modelParameter info what=models where=rawfile
element info what=inst where=rawfile
outputParameter info what=output where=rawfile
designParamVals info what=parameters where=rawfile
primitives info what=primitives where=rawfile
subckts info what=subckts where=rawfile

saveOptions options save=allpub rawfmt=psfbin
"""
