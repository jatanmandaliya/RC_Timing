*****
****RC Network****
******
.temp 25
.lib '/packages/process_kit/generic/generic_14nm/SAED14nm_PDK_12142021/SAED14_PDK/hspice/saed14nm.lib' TT
.subckt inverter avdd avss vin vout
xm0 vout vin avdd avdd p08 l=0.016u nf=1 m=1 nfin=5
xm2 vout vin avss avss n08 l=0.016u nf=1 nfin=5
.ends inverter
xi0 avdd 0 in 1 inverter
vdd avdd 0 dc=0.8
vin in 0 dc=0 pulse ( 0 0.8 0.1n 10p 10p 10n 20n )
R1 1 2 11.7242
C1 1 0 1.07296e-15
C2 2 0 1.8927e-14
.tran 10p 100n start=0
.options list node post
.end
