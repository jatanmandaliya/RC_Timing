#!/usr/bin/env python3
# lumped_c_gui.py — minimal GUI to compute Lumped-C from manual inputs (ground caps only)

import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog

from datetime import datetime

def parse_float_list(csv_text: str):
    csv_text = csv_text.strip()
    if not csv_text:
        return []
    try:
        return [float(x.strip()) for x in csv_text.split(",") if x.strip()]
    except ValueError as e:
        raise ValueError("Enter numbers as plain floats (e.g., 1e-15,2e-15).")

def write_reduced_spef(path: str, net: str, root_node: str, C_eq: float):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "w") as f:
        f.write('*SPEF "IEEE 1481-1999"\n')
        f.write(f"*DESIGN lumped_c_gui\n*DATE {now}\n*VENDOR script\n")
        f.write("*DIVIDER /\n*DELIMITER :\n*BUS_DELIMITER [ ]\n")
        f.write("*T_UNIT 1\n*C_UNIT 1\n*R_UNIT 1\n")
        f.write(f"*D_NET {net} {C_eq:g}\n")
        f.write("*CONN\n")
        f.write("*CAP\n")
        f.write(f"1 {root_node} {C_eq:g}\n")
        f.write("*RES\n")
        f.write("*END\n")

def write_spice_tb(path: str, C_eq: float, Rdrv: float, VDD: float):
    with open(path, "w") as f:
        f.write(f"* Lumped-C testbench (manual)\n")
        f.write(f".param VDD={VDD}\n")
        f.write(f"VSTEP in 0 PULSE(0 VDD 0 1p 1p 50p 100p)\n")
        f.write(f"RDRV in n1 {Rdrv:g}\n")
        f.write(f"CLOAD n1 0 {C_eq:g}\n")
        f.write(f".tran 1p 2n\n")
        f.write(f".probe v(in) v(n1)\n")
        f.write(f".end\n")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Lumped-C (manual)")
        self.geometry("560x360")
        self.resizable(False, False)

        # Inputs
        row = 0
        tk.Label(self, text="Ground Caps Cs (floats, comma-separated):").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.cs_entry = tk.Entry(self, width=60)
        self.cs_entry.grid(row=row, column=1, padx=10, pady=6)
        row += 1

        tk.Label(self, text="Resistors Rs (optional, floats):").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.rs_entry = tk.Entry(self, width=60)
        self.rs_entry.grid(row=row, column=1, padx=10, pady=6)
        row += 1

        tk.Label(self, text="Driver Rdrv (ohms):").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.rdrv_entry = tk.Entry(self, width=20)
        self.rdrv_entry.insert(0, "100")
        self.rdrv_entry.grid(row=row, column=1, sticky="w", padx=10, pady=6)
        row += 1

        tk.Label(self, text="VDD (V):").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.vdd_entry = tk.Entry(self, width=20)
        self.vdd_entry.insert(0, "1.0")
        self.vdd_entry.grid(row=row, column=1, sticky="w", padx=10, pady=6)
        row += 1

        tk.Label(self, text="Net name:").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.net_entry = tk.Entry(self, width=30)
        self.net_entry.insert(0, "MANUAL_NET")
        self.net_entry.grid(row=row, column=1, sticky="w", padx=10, pady=6)
        row += 1

        tk.Label(self, text="Root node (driver):").grid(row=row, column=0, sticky="w", padx=10, pady=6)
        self.root_entry = tk.Entry(self, width=30)
        self.root_entry.insert(0, "MANUAL_NET:ROOT")
        self.root_entry.grid(row=row, column=1, sticky="w", padx=10, pady=6)
        row += 1

        # Actions
        self.ceq_var = tk.StringVar(value="C_eq = ?")
        tk.Button(self, text="Compute Lumped C", command=self.compute).grid(row=row, column=0, padx=10, pady=10, sticky="w")
        tk.Label(self, textvariable=self.ceq_var, font=("Segoe UI", 11, "bold")).grid(row=row, column=1, padx=10, pady=10, sticky="w")
        row += 1

        tk.Button(self, text="Save reduced SPEF...", command=self.save_spef).grid(row=row, column=0, padx=10, pady=6, sticky="w")
        tk.Button(self, text="Save SPICE testbench...", command=self.save_spice).grid(row=row, column=1, padx=10, pady=6, sticky="w")
        row += 1

        self.current_ceq = None  # cache after compute

    def compute(self):
        try:
            Cs = parse_float_list(self.cs_entry.get())
            _ = parse_float_list(self.rs_entry.get()) if self.rs_entry.get().strip() else []
            if not Cs:
                messagebox.showerror("Input error", "Enter at least one ground capacitor in Cs.")
                return
            C_eq = sum(Cs)  # ground only; coupling is intentionally ignored
            self.current_ceq = C_eq
            self.ceq_var.set(f"C_eq = {C_eq:g} F")
        except Exception as e:
            messagebox.showerror("Input error", str(e))

    def get_common(self):
        net = self.net_entry.get().strip() or "MANUAL_NET"
        root_node = self.root_entry.get().strip() or f"{net}:ROOT"
        try:
            rdrv = float(self.rdrv_entry.get().strip())
            vdd = float(self.vdd_entry.get().strip())
        except ValueError:
            raise ValueError("Rdrv and VDD must be floats.")
        return net, root_node, rdrv, vdd

    def save_spef(self):
        if self.current_ceq is None:
            self.compute()
            if self.current_ceq is None:
                return
        try:
            net, root_node, _, _ = self.get_common()
            path = filedialog.asksaveasfilename(defaultextension=".spef", filetypes=[("SPEF files","*.spef"),("All files","*.*")], initialfile=f"{net}_lumped.spef")
            if not path:
                return
            write_reduced_spef(path, net, root_node, self.current_ceq)
            messagebox.showinfo("Saved", f"Reduced SPEF written:\n{path}")
        except Exception as e:
            messagebox.showerror("Save error", str(e))

    def save_spice(self):
        if self.current_ceq is None:
            self.compute()
            if self.current_ceq is None:
                return
        try:
            _, _, rdrv, vdd = self.get_common()
            path = filedialog.asksaveasfilename(defaultextension=".sp", filetypes=[("SPICE files","*.sp;*.cir;*.ckt"),("All files","*.*")], initialfile="lumped_tb.sp")
            if not path:
                return
            write_spice_tb(path, self.current_ceq, rdrv, vdd)
            messagebox.showinfo("Saved", f"SPICE testbench written:\n{path}")
        except Exception as e:
            messagebox.showerror("Save error", str(e))

if __name__ == "__main__":
    App().mainloop()
