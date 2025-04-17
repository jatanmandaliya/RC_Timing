class Node:
    def __init__(self, component_type, value):
        self.component_type = component_type
        self.value = value
        self.next = None


class LinkedList:
    def __init__(self):
        self.head = None

    def append(self, component_type, value):
        if not self.head:
            self.head = Node(component_type, value)
        else:
            current = self.head
            while current.next:
                current = current.next
            current.next = Node(component_type, value)


def parse_hspice_file(filename):
    linked_list = LinkedList()
    with open(filename, "r") as f:
        lines = f.readlines()
        for line in lines:
            line = line.strip()
            if line.startswith("R") or line.startswith("C"):
                parts = line.split()
                if len(parts) >= 4:
                    component_type = parts[0][0]
                    try:
                        value = float(parts[3])  # Value is directly in ohms or farads
                        linked_list.append(component_type, value)
                    except ValueError:
                        pass  # Skip if value cannot be converted to float

    return linked_list


def apply_rules(linked_list):
    # Initialize downstream values
    YD_1, YD_2, YD_3 = 0.0, 0.0, 0.0

    # Initialize upstream values
    YU_1, YU_2, YU_3 = YD_1, YD_2, YD_3

    current = linked_list.head
    while current:
        if current.component_type == "C":  # Rule #1: Lumped Capacitor
            C = current.value
            YU_1 += C
            # YU_2 and YU_3 remain unchanged
        elif current.component_type == "R":  # Rule #2: Lumped Resistor
            R = current.value
            YU_2 -= R * (YU_1 ** 2)
            YU_3 -= 2 * R * YU_1 * YU_2 + R ** 2 * (YU_1 ** 3)

        current = current.next

    return YU_1, YU_2, YU_3


def convert_to_pi_model(YU_1, YU_2, YU_3):
    C2 = YU_2 ** 2 / YU_3
    C1 = YU_1 - ((YU_2 ** 2) / YU_3)
    R1 = -((YU_3 ** 2) / (YU_2 ** 3))
    return R1, C1, C2


def generate_pi_model_spice_file(input_file, output_file, R1, C1, C2):
    # Read the original file to preserve structure and content
    with open(input_file, "r") as f:
        original_lines = f.readlines()

    # Process the file by identifying different sections
    subckt_lines = []
    subckt_section = False
    inverter_ends_found = False

    header_lines = []
    circuit_lines = []
    rc_section_found = False
    footer_lines = []

    # Find the node where the RC network begins
    start_node = "1"  # Default if we can't determine

    for line in original_lines:
        line_stripped = line.strip()

        # Handle subcircuit section
        if line_stripped.startswith(".subckt"):
            subckt_section = True
            subckt_lines.append(line)
        elif subckt_section and not inverter_ends_found and line_stripped.startswith(".ends"):
            subckt_lines.append(line)
            subckt_section = False
            inverter_ends_found = True
        elif subckt_section:
            subckt_lines.append(line)

        # Handle other sections
        elif line_stripped.startswith(".temp") or line_stripped.startswith(".lib"):
            header_lines.append(line)
        elif line_stripped.startswith("xi0") or line_stripped.startswith("vdd") or line_stripped.startswith("vin"):
            circuit_lines.append(line)
            # Try to find the output node of the inverter
            if line_stripped.startswith("xi0"):
                parts = line_stripped.split()
                if len(parts) >= 5:
                    start_node = parts[4]  # Output node of inverter
        elif line_stripped.startswith("R") or line_stripped.startswith("C"):
            rc_section_found = True
        elif line_stripped.startswith(".tran") or line_stripped.startswith(".options") or line_stripped.startswith(
                ".end"):
            footer_lines.append(line)

    # Create the new file with Pi model
    with open(output_file, "w") as f:
        # Write header with comment
        f.write("*****\n****RC Network****\n******\n")

        # Write header lines
        for line in header_lines:
            f.write(line)

        # Write subcircuit definition
        for line in subckt_lines:
            f.write(line)

        # Write circuit components before RC network
        for line in circuit_lines:
            f.write(line)

        # Write Pi model components with specified node numbering
        f.write(f"R1 {start_node} 2 {R1:.6g}\n")
        f.write(f"C1 {start_node} 0 {C1:.6g}\n")
        f.write(f"C2 2 0 {C2:.6g}\n")

        # Write footer
        for line in footer_lines:
            f.write(line)

        # Ensure there's an .end statement if none was found
        if not any(line.strip().startswith(".end") for line in footer_lines):
            f.write(".end\n")


def save_pi_model_values(YU_1, YU_2, YU_3, R1, C1, C2):
    with open("pi_model_values.txt", "w") as f:
        f.write("Pi Model Values:\n")
        f.write(f"YU1 = {YU_1}\n")
        f.write(f"YU2 = {YU_2}\n")
        f.write(f"YU3 = {YU_3}\n")
        f.write("\nFinal Component Values:\n")
        f.write(f"R1 = {R1}\n")
        f.write(f"C1 = {C1}\n")
        f.write(f"C2 = {C2}\n")


# Main execution flow
input_file = "rc_network.sp"
output_file = "rc_network_pi_model.sp"

# Parse the HSPICE file into a linked list
linked_list = parse_hspice_file(input_file)

# Apply rules to calculate upstream traversal values (YU)
YU_1, YU_2, YU_3 = apply_rules(linked_list)

# Convert to π model to find R1, C1, and C2
R1, C1, C2 = convert_to_pi_model(YU_1, YU_2, YU_3)

# Print final results
print("Final Upstream Values:")
print(f"YU_1 = {YU_1}")
print(f"YU_2 = {YU_2}")
print(f"YU_3 = {YU_3}")

print("\nFinal Component Values:")
print(f"R1 = {R1}")
print(f"C1 = {C1}")
print(f"C2 = {C2}")

# Generate the new SPICE file with Pi model
generate_pi_model_spice_file(input_file, output_file, R1, C1, C2)
print(f"\nGenerated Pi model SPICE file: {output_file}")

# Save results to a file
save_pi_model_values(YU_1, YU_2, YU_3, R1, C1, C2)
