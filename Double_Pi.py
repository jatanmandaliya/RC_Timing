#!/usr/bin/env python3
# double_pi_gui.py — GUI to compute a Double-π equivalent from manual Rs/Cs.
# Modified to handle any number of resistors and capacitors independently.

import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path
import math


# ---------- helpers ----------
def parse_list(csv: str):
    csv = csv.strip()
    if not csv:
        return []
    try:
        return [float(x.strip()) for x in csv.split(",") if x.strip()]
    except ValueError:
        raise ValueError("Enter comma-separated floats (e.g., 50,75,30).")


# ---------- exact detection: "already double-π" ----------
def detect_exact_double_pi(Rs, Cs, tol=1e-12):
    """
    Simple and robust grouping for double-pi topology.

    Logic:
    1. Find exactly 2 non-zero resistors (R1, R2)
    2. Group capacitors into 3 sections based on position
    3. Sum capacitors in each section

    Works for any len(Cs) and len(Rs) relationship.
    """
    # Find non-zero resistors and their positions
    nz_data = [(i, R) for i, R in enumerate(Rs) if abs(R) >= tol]
    if len(nz_data) != 2:
        return None  # need exactly 2 non-zero resistors

    (i1, R1), (i2, R2) = nz_data

    # Simple sectioning approach:
    # Divide capacitor array into 3 roughly equal sections
    # This works regardless of the relationship between len(Cs) and len(Rs)

    n_caps = len(Cs)
    if n_caps < 3:
        return None  # need at least 3 capacitors

    # Calculate section boundaries
    section_size = n_caps // 3
    remainder = n_caps % 3

    # Distribute remainder among first sections
    if remainder == 0:
        # Equal sections: [0:s], [s:2s], [2s:end]
        b1, b2 = section_size, 2 * section_size
    elif remainder == 1:
        # Give extra to first section: [0:s+1], [s+1:2s+1], [2s+1:end]
        b1, b2 = section_size + 1, 2 * section_size + 1
    else:  # remainder == 2
        # Give extra to first two: [0:s+1], [s+1:2s+2], [2s+2:end]
        b1, b2 = section_size + 1, 2 * section_size + 2

    # Sum capacitors in each section
    C1 = sum(Cs[0:b1])
    C2 = sum(Cs[b1:b2])
    C3 = sum(Cs[b2:])

    # Sanity check: keep passive
    if R1 <= 0 or R2 <= 0 or C1 < 0 or C2 < 0 or C3 < 0:
        return None

    return R1, R2, C1, C2, C3


# ---------- generalized moments calculation ----------
def calculate_moments_flexible(Rs, Cs):
    """
    Calculate moments for flexible Rs and Cs arrays.
    Uses upstream traversal rules similar to the original code.
    """
    # Initialize downstream values
    y1, y2, y3 = 0.0, 0.0, 0.0

    # Process all capacitors first (can be done in any order for moment calculation)
    for C in Cs:
        y1 += C

    # Process all resistors using upstream rules
    for R in Rs:
        if abs(R) > 1e-15:  # Skip zero resistors
            y2 -= R * (y1 ** 2)
            y3 -= 2.0 * R * y1 * y2 + (R ** 2) * (y1 ** 3)

    return y1, y2, y3  # m0, m1, m2


# ---------- moment-matched symmetric Double-π (robust) ----------
def _k2_from(alpha, beta):
    S = (1.0 - alpha)
    a = alpha
    b = beta
    return (b ** 2) * (S ** 3) + 2 * b * (1 - b) * (S * (a ** 2)) + ((1 - b) ** 2) * (a ** 3)


def solve_double_pi_sym(Rtot, Ctot, m1, m2, *, tol=1e-10):
    R, C = Rtot, Ctot
    if R <= 0 or C <= 0:
        raise ValueError("Totals must be positive.")
    k1 = -m1 / (R * C * C)
    k2_target = m2 / (R * R * C * C * C)

    def beta_from_alpha(alpha):
        d = 1.0 - 2.0 * alpha
        if abs(d) < 1e-15:
            return None
        return (k1 - alpha * alpha) / d

    eps = 1e-6
    best = None  # (err, alpha, beta)
    for i in range(1200):
        alpha = eps + (0.5 - 2 * eps) * (i / 1199.0)
        beta = beta_from_alpha(alpha)
        if beta is None or not math.isfinite(beta):
            continue
        if not (0.0 < beta < 1.0):
            continue
        if (1.0 - 2.0 * alpha) < 0.0:
            continue
        err = abs(_k2_from(alpha, beta) - k2_target)
        if best is None or err < best[0]:
            best = (err, alpha, beta)

    if best is None:
        alpha = 0.25
        beta = beta_from_alpha(alpha)
        if beta is None or not math.isfinite(beta):
            beta = 0.5
        beta = min(0.999999, max(0.000001, beta))
        resid = float("inf")
        used_fallback = True
    else:
        resid, alpha, beta = best
        used_fallback = resid > tol

    C1 = C3 = alpha * C
    C2 = (1.0 - 2.0 * alpha) * C
    R1 = beta * R
    R2 = (1.0 - beta) * R

    if C1 <= 0 or C2 < 0 or C3 <= 0 or R1 <= 0 or R2 <= 0:
        alpha = 0.25;
        beta = 0.5
        C1 = C3 = alpha * C
        C2 = (1.0 - 2.0 * alpha) * C
        R1 = beta * R
        R2 = (1.0 - beta) * R
        resid = float("inf")
        used_fallback = True

    return R1, R2, C1, C2, C3, (resid if math.isfinite(resid) else None), used_fallback


# ---------- SPICE deck (golden vs Double-π) ----------
def write_spice_double_pi(path, Rs, Cs, Rdrv, R1, R2, C1, C2, C3,
                          VDD=1.0, tr="1p", tf="1p", pw="50p", per="100p",
                          tstep="1p", tstop="2n"):
    with open(path, "w") as f:
        f.write("* GOLDEN network vs Double-PI (GUI)\n")
        f.write(f".param VDD={VDD}\n")
        f.write(f"VSTEP in 0 PULSE(0 'VDD' 0 {tr} {tf} {pw} {per})\n")

        f.write("\n* --- GOLDEN network ---\n")
        f.write(f"RDRV_G in ng0 {Rdrv:g}\n")

        # Write capacitors - ensure we have nodes for them
        for i, Ci in enumerate(Cs):
            if Ci > 0:  # Only write non-zero capacitors
                f.write(f"CG{i} ng{i} 0 {Ci:g}\n")

        # Write resistors - ensure proper node connectivity
        last_node = len(Cs) - 1
        for i, Ri in enumerate(Rs):
            if i < last_node:  # Don't create nodes beyond what we have
                if Ri != 0:  # Only write non-zero resistors
                    f.write(f"RG{i} ng{i} ng{i + 1} {Ri:g}\n")
                else:
                    # For zero resistors, create a very small resistance to avoid shorts
                    f.write(f"RG{i} ng{i} ng{i + 1} 1m\n")

        f.write("\n* --- Double-PI ---\n")
        f.write(f"RDRV_P in np0 {Rdrv:g}\n")
        f.write(f"R1 np0 np1 {R1:g}\n")
        f.write(f"R2 np1 np2 {R2:g}\n")
        f.write(f"C1 np0 0 {C1:g}\n")
        f.write(f"C2 np1 0 {C2:g}\n")
        f.write(f"C3 np2 0 {C3:g}\n")

        f.write(f"\n.tran {tstep} {tstop}\n")
        f.write(f".measure tran t50_golden TRIG v(in) VAL='VDD/2' RISE=1 TARG v(ng{last_node}) VAL='VDD/2' RISE=1\n")
        f.write(f".measure tran t50_dpi    TRIG v(in) VAL='VDD/2' RISE=1 TARG v(np2) VAL='VDD/2' RISE=1\n")
        f.write(f".probe v(in) v(ng{last_node}) v(np2)\n")
        f.write(".end\n")


# ---------- GUI ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Flexible Double-π Model")
        self.geometry("780x540")
        self.resizable(False, False)

        r = 0
        tk.Label(self, text="Series Rs (ohm, comma-separated):").grid(row=r, column=0, sticky="w", padx=10, pady=8)
        self.rs_entry = tk.Entry(self, width=70);
        self.rs_entry.insert(0, "10,20,30")
        self.rs_entry.grid(row=r, column=1, padx=10, pady=8);
        r += 1

        tk.Label(self, text="Shunt Cs (F, comma-separated):").grid(row=r, column=0, sticky="w", padx=10, pady=8)
        self.cs_entry = tk.Entry(self, width=70);
        self.cs_entry.insert(0, "1e-12,2e-12,3e-12,4e-12")
        self.cs_entry.grid(row=r, column=1, padx=10, pady=8);
        r += 1

        tk.Label(self, text="Driver Rdrv (ohm):").grid(row=r, column=0, sticky="w", padx=10, pady=8)
        self.rdrv_entry = tk.Entry(self, width=18);
        self.rdrv_entry.insert(0, "100")
        self.rdrv_entry.grid(row=r, column=1, sticky="w", padx=10, pady=8);
        r += 1

        tk.Label(self, text="VDD (V):").grid(row=r, column=0, sticky="w", padx=10, pady=8)
        self.vdd_entry = tk.Entry(self, width=18);
        self.vdd_entry.insert(0, "1.0")
        self.vdd_entry.grid(row=r, column=1, sticky="w", padx=10, pady=8);
        r += 1

        tk.Label(self, text="Transient (tstep / tstop):").grid(row=r, column=0, sticky="w", padx=10, pady=8)
        tfrm = tk.Frame(self);
        tfrm.grid(row=r, column=1, sticky="w", padx=10, pady=8)
        tk.Label(tfrm, text="tstep").grid(row=0, column=0)
        self.tstep_entry = tk.Entry(tfrm, width=12);
        self.tstep_entry.insert(0, "1p");
        self.tstep_entry.grid(row=0, column=1, padx=6)
        tk.Label(tfrm, text="tstop").grid(row=0, column=2)
        self.tstop_entry = tk.Entry(tfrm, width=12);
        self.tstop_entry.insert(0, "2n");
        self.tstop_entry.grid(row=0, column=3, padx=6)
        r += 1

        tk.Button(self, text="Compute Double-π", command=self.compute).grid(row=r, column=0, sticky="w", padx=10,
                                                                            pady=12)
        self.res_var = tk.StringVar(value="R1=?, R2=?\nC1=?, C2=?, C3=?")
        tk.Label(self, textvariable=self.res_var, font=("Segoe UI", 11, "bold"),
                 justify="left").grid(row=r, column=1, sticky="w", padx=10, pady=12)
        r += 1

        # Add info label
        info_text = "Note: This version accepts any number of Rs and Cs independently.\nNo requirement for len(Cs) = len(Rs) + 1."
        tk.Label(self, text=info_text, font=("Segoe UI", 9), fg="blue",
                 justify="left").grid(row=r, column=0, columnspan=2, sticky="w", padx=10, pady=8)
        r += 1

        tk.Button(self, text="Save SPICE deck…", command=self.save_spice).grid(row=r, column=0, sticky="w", padx=10,
                                                                               pady=8)
        self.current = None  # (R1,R2,C1,C2,C3,Rs,Cs,Rdrv,VDD, from_exact)

    def compute(self):
        try:
            Rs = parse_list(self.rs_entry.get())
            Cs = parse_list(self.cs_entry.get())

            # Remove the restriction - allow any number of Rs and Cs
            if not Rs and not Cs:
                raise ValueError("Please enter at least one resistor or capacitor value.")

            # Handle empty arrays
            if not Rs:
                Rs = [0.0]  # Add a dummy zero resistor
            if not Cs:
                Cs = [1e-15]  # Add a tiny dummy capacitor

            Rdrv = float(self.rdrv_entry.get().strip());
            VDD = float(self.vdd_entry.get().strip())

            # 1) try exact detection (simplified for flexible arrays)
            exact = None
            if len(Rs) >= 2:  # Need at least 2 resistors for double-π
                exact = detect_exact_double_pi(Rs, Cs)

            if exact is not None:
                R1, R2, C1, C2, C3 = exact
                from_exact = True
            else:
                # 2) otherwise moment-matched symmetric fallback
                m0, m1, m2 = calculate_moments_flexible(Rs, Cs)
                Rtot, Ctot = sum(Rs), sum(Cs)

                if Rtot <= 0:
                    Rtot = 1.0  # Set minimum resistance
                if Ctot <= 0:
                    Ctot = 1e-15  # Set minimum capacitance

                R1, R2, C1, C2, C3, resid, used_fallback = solve_double_pi_sym(Rtot, Ctot, m1, m2)
                from_exact = False
                if used_fallback:
                    messagebox.showwarning(
                        "Note",
                        "Exact symmetric Double-π match wasn't feasible.\n"
                        "Returned a best-effort passive fit."
                    )

            self.current = (R1, R2, C1, C2, C3, Rs, Cs, Rdrv, VDD, from_exact)
            tag = " (exact)" if from_exact else " (fit)"
            self.res_var.set(f"R1 = {R1:.6g} Ω,  R2 = {R2:.6g} Ω{tag}\n"
                             f"C1 = {C1:.6g} F\nC2 = {C2:.6g} F\nC3 = {C3:.6g} F")
        except Exception as e:
            messagebox.showerror("Input error", str(e))

    def save_spice(self):
        if self.current is None:
            self.compute()
            if self.current is None:
                return
        R1, R2, C1, C2, C3, Rs, Cs, Rdrv, VDD, _ = self.current
        path = filedialog.asksaveasfilename(
            defaultextension=".sp", initialfile="double_pi_vs_golden.sp",
            filetypes=[("SPICE files", "*.sp;*.cir;*.ckt"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            write_spice_double_pi(Path(path), Rs, Cs, Rdrv, R1, R2, C1, C2, C3,
                                  VDD=VDD, tstep=self.tstep_entry.get().strip() or "1p",
                                  tstop=self.tstop_entry.get().strip() or "2n")
            messagebox.showinfo("Saved", f"SPICE deck written:\n{path}\n\nMeasures t50_golden vs t50_dpi.")
        except Exception as e:
            messagebox.showerror("Save error", str(e))


if __name__ == "__main__":
    App().mainloop()