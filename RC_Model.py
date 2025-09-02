import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path

# ---------- math helpers ----------
def parse_list(csv_text: str):
    csv_text = csv_text.strip()
    if not csv_text:
        return []
    try:
        return [float(x.strip()) for x in csv_text.split(",") if x.strip()]
    except ValueError:
        raise ValueError("Enter comma-separated floats (e.g., 50,75,30).")

def ceq_from(Cs):
    return sum(Cs)

def sum_C_times_Rup(Rs, Cs, Rdrv):
    """
    Supports two forms:
      - len(Cs) == len(Rs)+1 (ladder: C at every node including driver node)
      - len(Cs) == len(Rs)   (C only at internal/load nodes)
    """
    if not (len(Cs) == len(Rs) or len(Cs) == len(Rs) + 1):
        raise ValueError("Require len(Cs) = len(Rs) or len(Cs) = len(Rs)+1.")

    total = 0.0
    Rup = Rdrv
    for i, Ci in enumerate(Cs):
        total += Ci * Rup
        if i < len(Rs):  # advance past Ri
            Rup += Rs[i]
    return total

def rc_equivalent(Rs, Cs, Rdrv):
    """
    Compute Req, Ceq from arbitrary ladder-like RC.
    Works for len(Cs) = len(Rs) or len(Cs) = len(Rs)+1.
    """
    Ceq = ceq_from(Cs)
    if Ceq <= 0.0:
        raise ValueError("Sum of capacitors must be > 0.")

    sumCR = sum_C_times_Rup(Rs, Cs, Rdrv)
    Req = sumCR / Ceq
    return Req, Ceq, sumCR

# ---------- SPICE writer ----------
def write_spice_deck(path, Rs, Cs, Rdrv, VDD,
                     tr="1p", tf="1p", pw="50p", per="100p",
                     tstep="1p", tstop="2n"):
    """
    Makes 1 deck with two branches driven by the same source:
      - GOLDEN ladder-like RC network
      - RC equivalent: Rdrv -> Req -> Ceq
    Measures t50 on both waveforms.
    """
    Req, Ceq, _ = rc_equivalent(Rs, Cs, Rdrv)
    N = len(Rs)
    with open(path, "w") as f:
        f.write("* RC equivalent vs GOLDEN ladder (GUI generated)\n")
        f.write(f".param VDD={VDD}\n")
        f.write(f"VSTEP in 0 PULSE(0 VDD 0 {tr} {tf} {pw} {per})\n")

        f.write("\n* --- GOLDEN ---\n")
        f.write(f"RDRV_G in ng0 {Rdrv:g}\n")
        for i, Ci in enumerate(Cs):
            f.write(f"CG{i} ng{i} 0 {Ci:g}\n")
        for i, Ri in enumerate(Rs, start=1):
            f.write(f"RG{i} ng{i-1} ng{i} {Ri:g}\n")

        f.write("\n* --- RC equivalent ---\n")
        f.write(f"RDRV_R in nr0 {Rdrv:g}\n")
        f.write(f"RREQ  nr0 nr1 {Req:g}\n")
        f.write(f"CREQ  nr1 0 {Ceq:g}\n")
        f.write(f"* Computed: Req={Req:g} ohm, Ceq={Ceq:g} F\n")

        f.write(f"\n.tran {tstep} {tstop}\n")
        f.write(f".measure tran t50_golden TRIG v(in)  VAL='VDD/2' RISE=1  "
                f"TARG v(ng{N}) VAL='VDD/2' RISE=1\n")
        f.write(f".measure tran t50_rc     TRIG v(in)  VAL='VDD/2' RISE=1  "
                f"TARG v(nr1)  VAL='VDD/2' RISE=1\n")
        f.write(f".probe v(in) v(ng{N}) v(nr1)\n")
        f.write(".end\n")

# ---------- GUI ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RC Equivalent (manual)")
        self.geometry("620x420")
        self.resizable(False, False)

        row = 0
        tk.Label(self, text="Series Rs (ohm, comma-separated):").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.rs_entry = tk.Entry(self, width=60)
        self.rs_entry.insert(0, "50,75,30")
        self.rs_entry.grid(row=row, column=1, padx=10, pady=8); row += 1

        tk.Label(self, text="Shunt Cs (F, comma-separated)  (len(Cs) = len(Rs) or len(Rs)+1):").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.cs_entry = tk.Entry(self, width=60)
        self.cs_entry.insert(0, "1e-15,2e-15,1.5e-15,3e-15")
        self.cs_entry.grid(row=row, column=1, padx=10, pady=8); row += 1

        tk.Label(self, text="Driver Rdrv (ohm):").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.rdrv_entry = tk.Entry(self, width=20)
        self.rdrv_entry.insert(0, "100")
        self.rdrv_entry.grid(row=row, column=1, sticky="w", padx=10, pady=8); row += 1

        tk.Label(self, text="VDD (V):").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.vdd_entry = tk.Entry(self, width=20)
        self.vdd_entry.insert(0, "1.0")
        self.vdd_entry.grid(row=row, column=1, sticky="w", padx=10, pady=8); row += 1

        # transient options (optional)
        tk.Label(self, text="Transient (step/stop):").grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.tstep_entry = tk.Entry(self, width=12); self.tstep_entry.insert(0, "1p")
        self.tstop_entry = tk.Entry(self, width=12); self.tstop_entry.insert(0, "2n")
        tfrm = tk.Frame(self); tfrm.grid(row=row, column=1, sticky="w", padx=10, pady=8)
        tk.Label(tfrm, text="tstep").grid(row=0, column=0); self.tstep_entry.grid(row=0, column=1, padx=6)
        tk.Label(tfrm, text="tstop").grid(row=0, column=2); self.tstop_entry.grid(row=0, column=3, padx=6)
        row += 1

        tk.Button(self, text="Compute RC", command=self.compute).grid(row=row, column=0, sticky="w", padx=10, pady=10)
        self.res_var = tk.StringVar(value="Req = ?,  Ceq = ?")
        tk.Label(self, textvariable=self.res_var, font=("Segoe UI", 11, "bold")).grid(row=row, column=1, sticky="w", padx=10, pady=10)
        row += 1

        tk.Button(self, text="Save SPICE deck…", command=self.save_spice).grid(row=row, column=0, sticky="w", padx=10, pady=6)
        row += 1

        self.current = None  # (Req, Ceq, Rs, Cs, Rdrv, VDD)

    def compute(self):
        try:
            Rs = parse_list(self.rs_entry.get())
            Cs = parse_list(self.cs_entry.get())
            Rdrv = float(self.rdrv_entry.get().strip())
            VDD  = float(self.vdd_entry.get().strip())
            Req, Ceq, _ = rc_equivalent(Rs, Cs, Rdrv)
            self.current = (Req, Ceq, Rs, Cs, Rdrv, VDD)
            self.res_var.set(f"Req = {Req:g} Ω,   Ceq = {Ceq:g} F")
        except Exception as e:
            messagebox.showerror("Input error", str(e))

    def save_spice(self):
        if self.current is None:
            self.compute()
            if self.current is None: return
        Req, Ceq, Rs, Cs, Rdrv, VDD = self.current
        # user picks file name
        path = filedialog.asksaveasfilename(defaultextension=".sp",
                                            initialfile="rc_vs_golden.sp",
                                            filetypes=[("SPICE files","*.sp;*.cir;*.ckt"), ("All files","*.*")])
        if not path: return
        try:
            write_spice_deck(Path(path), Rs, Cs, Rdrv, VDD,
                             tstep=self.tstep_entry.get().strip() or "1p",
                             tstop=self.tstop_entry.get().strip() or "2n")
            messagebox.showinfo("Saved", f"SPICE deck written:\n{path}\n\nMeasures t50_golden vs t50_rc.")
        except Exception as e:
            messagebox.showerror("Save error", str(e))

if __name__ == "__main__":
    App().mainloop()
