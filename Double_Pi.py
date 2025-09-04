#!/usr/bin/env python3
# double_pi_parser.py - Parse SPICE file and compute Double-π equivalent
# Similar structure to PI_MODEL.py but for Double-π networks

class Node:
    def __init__(self, component_type, value, node1=None, node2=None):
        self.component_type = component_type
        self.value = value
        self.node1 = node1
        self.node2 = node2
        self.next = None


class LinkedList:
    def __init__(self):
        self.head = None

    def append(self, component_type, value, node1=None, node2=None):
        if not self.head:
            self.head = Node(component_type, value, node1, node2)
        else:
            current = self.head
            while current.next:
                current = current.next
            current.next = Node(component_type, value, node1, node2)


def parse_hspice_file(filename):
    """
    Parse SPICE file and extract resistors and capacitors.
    Returns two lists: Rs (resistors) and Cs (capacitors) in order.
    """
    linked_list = LinkedList()
    components = []

    with open(filename, "r") as f:
        lines = f.readlines()
        for line in lines:
            line = line.strip()
            if line.startswith("R") or line.startswith("C"):
                parts = line.split()
                if len(parts) >= 4:
                    component_name = parts[0]
                    component_type = parts[0][0]  # 'R' or 'C'
                    node1 = parts[1]
                    node2 = parts[2]
                    try:
                        value = float(parts[3])
                        components.append((component_name, component_type, value, node1, node2))
                        linked_list.append(component_type, value, node1, node2)
                    except ValueError:
                        pass  # Skip if value cannot be converted to float

    # Sort components by name to maintain order (R1, R2, C1, C2, etc.)
    components.sort(key=lambda x: x[0])

    # Separate into resistors and capacitors lists
    Rs = []
    Cs = []

    for comp in components:
        comp_name, comp_type, value, n1, n2 = comp
        if comp_type == 'R':
            Rs.append(value)
        elif comp_type == 'C':
            Cs.append(value)

    return linked_list, Rs, Cs, components


def detect_exact_double_pi_from_spice(components, tol=1e-12):
    """
    Analyze SPICE components to detect double-π structure.
    Groups capacitors based on actual circuit topology with zero-ohm shorts.
    """
    # Build node-to-components mapping
    node_caps = {}  # node -> list of capacitor values
    all_resistors = []  # (from_node, to_node, value)

    for comp_name, comp_type, value, node1, node2 in components:
        if comp_type == 'C':
            # Capacitor from node to ground
            if node2 == '0':  # to ground
                if node1 not in node_caps:
                    node_caps[node1] = []
                node_caps[node1].append(value)
            elif node1 == '0':  # from ground (reverse)
                if node2 not in node_caps:
                    node_caps[node2] = []
                node_caps[node2].append(value)
        elif comp_type == 'R':
            all_resistors.append((node1, node2, value))

    # Find non-zero resistors
    nonzero_resistors = [(n1, n2, val) for n1, n2, val in all_resistors if abs(val) >= tol]
    zero_resistors = [(n1, n2, val) for n1, n2, val in all_resistors if abs(val) < tol]

    if len(nonzero_resistors) != 2:
        return None

    print(f"Debug: Non-zero resistors: {nonzero_resistors}")
    print(f"Debug: Zero resistors: {zero_resistors}")
    print(f"Debug: Node capacitors: {node_caps}")

    # Build zero-ohm connectivity groups
    def find_connected_nodes(start_node):
        """Find all nodes connected to start_node through zero-ohm resistors."""
        connected = {start_node}
        changed = True
        while changed:
            changed = False
            for n1, n2, val in zero_resistors:
                if n1 in connected and n2 not in connected:
                    connected.add(n2)
                    changed = True
                elif n2 in connected and n1 not in connected:
                    connected.add(n1)
                    changed = True
        return connected

    # Find all unique zero-ohm groups
    all_nodes = set()
    for n1, n2, val in all_resistors:
        if n1 != '0':
            all_nodes.add(n1)
        if n2 != '0':
            all_nodes.add(n2)

    visited = set()
    groups = []
    for node in all_nodes:
        if node not in visited:
            group = find_connected_nodes(node)
            group.discard('0')  # Remove ground
            if group:
                groups.append(group)
                visited.update(group)

    print(f"Debug: Zero-ohm connected groups: {[list(g) for g in groups]}")

    # Calculate capacitor sum for each group
    group_caps = []
    for group in groups:
        cap_sum = sum(sum(node_caps.get(node, [])) for node in group)
        group_caps.append((group, cap_sum))

    print(f"Debug: Groups with capacitor sums: {[(list(g), c) for g, c in group_caps]}")

    # Build adjacency based on non-zero resistors
    group_adjacency = {}

    for i, (group1, cap1) in enumerate(group_caps):
        group_adjacency[i] = []
        for r_from, r_to, r_val in nonzero_resistors:
            for j, (group2, cap2) in enumerate(group_caps):
                if i != j:
                    # Check if this resistor connects group i to group j
                    connects = False
                    if (r_from in group1 and r_to in group2) or (r_to in group1 and r_from in group2):
                        connects = True

                    if connects:
                        group_adjacency[i].append((j, r_val))

    print(f"Debug: Group adjacency: {group_adjacency}")

    # Find the linear path: start -> middle -> end
    # The middle group connects to 2 other groups, start and end connect to 1 each
    start_group = middle_group = end_group = None

    for i, connections in group_adjacency.items():
        if len(connections) == 2:
            middle_group = i
        elif len(connections) == 1:
            if start_group is None:
                start_group = i
            else:
                end_group = i

    if start_group is not None and middle_group is not None and end_group is not None:
        # Extract the results
        C1 = group_caps[start_group][1]
        C2 = group_caps[middle_group][1]
        C3 = group_caps[end_group][1]

        # Get resistor values by checking which resistors connect the groups
        R1 = R2 = None
        for r_from, r_to, r_val in nonzero_resistors:
            start_nodes = group_caps[start_group][0]
            middle_nodes = group_caps[middle_group][0]
            end_nodes = group_caps[end_group][0]

            if ((r_from in start_nodes and r_to in middle_nodes) or
                    (r_to in start_nodes and r_from in middle_nodes)):
                R1 = r_val
            elif ((r_from in middle_nodes and r_to in end_nodes) or
                  (r_to in middle_nodes and r_from in end_nodes)):
                R2 = r_val

        print(f"Debug: Final assignment - R1={R1}, R2={R2}, C1={C1}, C2={C2}, C3={C3}")

        if R1 is not None and R2 is not None and R1 > 0 and R2 > 0 and C1 >= 0 and C2 >= 0 and C3 >= 0:
            return R1, R2, C1, C2, C3

    return None


def apply_rules_reverse_linked_list(linked_list):
    """
    Apply upstream traversal rules using reverse linked list traversal.
    Start from the last component (which should be a capacitor) and work backwards.
    Returns y1, y2, y3, y4, y5 moments.
    """
    # First, collect all components into a list for reverse traversal
    components = []
    current = linked_list.head
    while current:
        components.append((current.component_type, current.value))
        current = current.next

    if not components:
        return 0.0, 0.0, 0.0, 0.0, 0.0

    # Initialize moments at downstream end
    y1 = y2 = y3 = y4 = y5 = 0.0

    # Start from the last component (should be capacitor)
    # Traverse in reverse order (upstream direction)
    for i in range(len(components) - 1, -1, -1):
        component_type, value = components[i]

        if component_type == "C":  # Capacitor rule
            y1 += value
            # y2, y3, y4, y5 remain unchanged for capacitor

        elif component_type == "R":  # Resistor rule
            R = value
            # Apply upstream resistor transformation rules
            y1_new = y1  # y1 unchanged for resistor
            y2_new = y2 - R * (y1 ** 2)
            y3_new = y3 - 2.0 * R * y1 * y2 + (R ** 2) * (y1 ** 3)
            y4_new = y4 - R * (2.0 * y1 * y3 + y2 ** 2) + 3.0 * (R ** 2) * (y1 ** 2) * y2 - (R ** 3) * (y1 ** 4)
            y5_new = (y5
                      - R * (2.0 * y1 * y4 + 2.0 * y2 * y3)
                      + (R ** 2) * (3.0 * (y1 ** 2) * y3 + 3.0 * y1 * (y2 ** 2))
                      - 4.0 * (R ** 3) * (y1 ** 3) * y2
                      + (R ** 4) * (y1 ** 5))

            y1, y2, y3, y4, y5 = y1_new, y2_new, y3_new, y4_new, y5_new

    return y1, y2, y3, y4, y5


def ladder_moments_up_to_5(Rs, Cs):
    """
    Compute the first five series coefficients of Y(s) at the driver:
      Y(s) = y1 s + y2 s^2 + y3 s^3 + y4 s^4 + y5 s^5 + ...
    Uses upstream traversal rules from the Double-Pi code.
    This is a fallback when linked list is not used.
    """
    if len(Cs) != len(Rs) + 1:
        # Handle flexible arrays - pad with zeros if needed
        if len(Cs) < len(Rs) + 1:
            Cs = Cs + [0.0] * (len(Rs) + 1 - len(Cs))
        elif len(Rs) < len(Cs) - 1:
            Rs = Rs + [0.0] * (len(Cs) - 1 - len(Rs))

    # Start at far end (node N)
    y1 = Cs[-1]
    y2 = y3 = y4 = y5 = 0.0

    # Walk upstream: for k = N-1..0
    for k in range(len(Rs) - 1, -1, -1):
        R = Rs[k]

        # Cross series resistor
        y1p = y1
        y2p = y2 - R * (y1 ** 2)
        y3p = y3 - 2.0 * R * y1 * y2 + (R ** 2) * (y1 ** 3)
        y4p = y4 - R * (2.0 * y1 * y3 + y2 ** 2) + 3.0 * (R ** 2) * (y1 ** 2) * y2 - (R ** 3) * (y1 ** 4)
        y5p = (y5
               - R * (2.0 * y1 * y4 + 2.0 * y2 * y3)
               + (R ** 2) * (3.0 * (y1 ** 2) * y3 + 3.0 * y1 * (y2 ** 2))
               - 4.0 * (R ** 3) * (y1 ** 3) * y2
               + (R ** 4) * (y1 ** 5))
        y1, y2, y3, y4, y5 = y1p, y2p, y3p, y4p, y5p

        # Then add the capacitor at this node k
        if k < len(Cs):
            y1 += Cs[k]

    return y1, y2, y3, y4, y5


def detect_exact_double_pi(Rs, Cs, tol=1e-12):
    """
    Detect if the network already represents a double-π structure.
    Returns (R1, R2, C1, C2, C3) if exact, None otherwise.
    (Fallback array-based method)
    """
    # Find non-zero resistors
    nz_indices = [i for i, R in enumerate(Rs) if abs(R) >= tol]
    if len(nz_indices) != 2:
        return None

    i1, i2 = nz_indices

    # Ensure we have enough capacitors
    if len(Cs) < 3:
        return None

    # Group capacitors based on resistor boundaries
    if len(Cs) == len(Rs) + 1:
        # Standard ladder format
        N = len(Cs) - 1
        C1 = sum(Cs[j] for j in range(0, i1 + 1))
        C2 = sum(Cs[j] for j in range(i1 + 1, i2 + 1))
        C3 = sum(Cs[j] for j in range(i2 + 1, N + 1))
    else:
        # Flexible format - divide into 3 sections
        n_caps = len(Cs)
        section_size = n_caps // 3
        remainder = n_caps % 3

        if remainder == 0:
            b1, b2 = section_size, 2 * section_size
        elif remainder == 1:
            b1, b2 = section_size + 1, 2 * section_size + 1
        else:  # remainder == 2
            b1, b2 = section_size + 1, 2 * section_size + 2

        C1 = sum(Cs[0:b1])
        C2 = sum(Cs[b1:b2])
        C3 = sum(Cs[b2:])

    R1 = Rs[i1]
    R2 = Rs[i2]

    if R1 <= 0 or R2 <= 0 or C1 < 0 or C2 < 0 or C3 < 0:
        return None
    return R1, R2, C1, C2, C3


def solve_double_pi_symmetric(Rtot, Ctot, m1, m2, tol=1e-10):
    """
    Solve for symmetric double-π using moment matching.
    Returns R1, R2, C1, C2, C3.
    """
    import math

    R, C = Rtot, Ctot
    if R <= 0 or C <= 0:
        raise ValueError("Totals must be positive.")

    k1 = -m1 / (R * C * C)
    k2_target = m2 / (R * R * C * C * C)

    def _k2_from(alpha, beta):
        S = (1.0 - alpha)
        a = alpha
        b = beta
        return (b ** 2) * (S ** 3) + 2 * b * (1 - b) * (S * (a ** 2)) + ((1 - b) ** 2) * (a ** 3)

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
        # Passive fallback
        alpha = 0.25
        beta = 0.5
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
        alpha = 0.25
        beta = 0.5
        C1 = C3 = alpha * C
        C2 = (1.0 - 2.0 * alpha) * C
        R1 = beta * R
        R2 = (1.0 - beta) * R
        resid = float("inf")
        used_fallback = True

    return R1, R2, C1, C2, C3, used_fallback


def generate_double_pi_spice_file(input_file, output_file, R1, R2, C1, C2, C3):
    """
    Generate new SPICE file with Double-π model replacing the original RC network.
    """
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

    # Create the new file with Double-π model
    with open(output_file, "w") as f:
        # Write header with comment
        f.write("*****\n****Double-π RC Network****\n******\n")

        # Write header lines
        for line in header_lines:
            f.write(line)

        # Write subcircuit definition
        for line in subckt_lines:
            f.write(line)

        # Write circuit components before RC network
        for line in circuit_lines:
            f.write(line)

        # Write Double-π model components
        f.write(f"R1 {start_node} 2 {R1:.6g}\n")
        f.write(f"R2 2 3 {R2:.6g}\n")
        f.write(f"C1 {start_node} 0 {C1:.6g}\n")
        f.write(f"C2 2 0 {C2:.6g}\n")
        f.write(f"C3 3 0 {C3:.6g}\n")

        # Write footer
        for line in footer_lines:
            f.write(line)

        # Ensure there's an .end statement if none was found
        if not any(line.strip().startswith(".end") for line in footer_lines):
            f.write(".end\n")


def save_double_pi_values(y1, y2, y3, y4, y5, R1, R2, C1, C2, C3, is_exact=False):
    """
    Save Double-π model values and moments to a text file.
    """
    with open("double_pi_values.txt", "w") as f:
        f.write("Double-π Model Values:\n")
        f.write("=" * 30 + "\n")
        f.write(f"Method: {'Exact' if is_exact else 'Moment-matched fit'}\n\n")

        f.write("Y(s) Series Coefficients (Moments):\n")
        f.write(f"y1 = {y1:.6g}\n")
        f.write(f"y2 = {y2:.6g}\n")
        f.write(f"y3 = {y3:.6g}\n")
        f.write(f"y4 = {y4:.6g}\n")
        f.write(f"y5 = {y5:.6g}\n\n")

        f.write("Final Double-π Component Values:\n")
        f.write(f"R1 = {R1:.6g} Ω\n")
        f.write(f"R2 = {R2:.6g} Ω\n")
        f.write(f"C1 = {C1:.6g} F\n")
        f.write(f"C2 = {C2:.6g} F\n")
        f.write(f"C3 = {C3:.6g} F\n")


# Main execution flow
def main():
    input_file = "rc_network.sp"
    output_file = "rc_network_double_pi_model.sp"

    try:
        # Parse the SPICE file
        print("Parsing SPICE file...")
        linked_list, Rs, Cs, components = parse_hspice_file(input_file)

        print(f"Found {len(Rs)} resistors and {len(Cs)} capacitors")
        print(f"Resistors: {Rs}")
        print(f"Capacitors: {Cs}")
        print(f"Components with nodes: {components}")

        # Calculate Y(s) moments using proper reverse linked list traversal
        print("\nCalculating Y(s) moments using reverse linked list traversal...")
        y1, y2, y3, y4, y5 = apply_rules_reverse_linked_list(linked_list)

        print("Y(s) Series Coefficients (from linked list):")
        print(f"y1 = {y1:.6g}")
        print(f"y2 = {y2:.6g}")
        print(f"y3 = {y3:.6g}")
        print(f"y4 = {y4:.6g}")
        print(f"y5 = {y5:.6g}")

        # Try exact detection using SPICE topology analysis first
        print("\nChecking for exact Double-π structure using topology analysis...")
        exact_result = detect_exact_double_pi_from_spice(components)

        if exact_result is not None:
            R1, R2, C1, C2, C3 = exact_result
            is_exact = True
            print("Found exact Double-π structure using topology analysis!")
        else:
            # Fallback: try array-based detection
            print("Topology analysis failed, trying array-based exact detection...")
            exact_result = detect_exact_double_pi(Rs, Cs)
            if exact_result is not None:
                R1, R2, C1, C2, C3 = exact_result
                is_exact = True
                print("Found exact Double-π structure using array method!")
            else:
                # Use moment-matched symmetric approach
                print("Using moment-matched symmetric Double-π...")
                Rtot, Ctot = sum(Rs), sum(Cs)
                m1, m2 = y2, y3  # Use y2, y3 as m1, m2 from linked list calculation
                R1, R2, C1, C2, C3, used_fallback = solve_double_pi_symmetric(Rtot, Ctot, m1, m2)
                is_exact = False
                if used_fallback:
                    print("Warning: Used fallback passive fit")

        # Print final results
        print("\nFinal Double-π Component Values:")
        print(f"R1 = {R1:.6g} Ω")
        print(f"R2 = {R2:.6g} Ω")
        print(f"C1 = {C1:.6g} F")
        print(f"C2 = {C2:.6g} F")
        print(f"C3 = {C3:.6g} F")
        print(f"Method: {'Exact' if is_exact else 'Moment-matched fit'}")

        # Generate the new SPICE file with Double-π model
        print(f"\nGenerating Double-π SPICE file: {output_file}")
        generate_double_pi_spice_file(input_file, output_file, R1, R2, C1, C2, C3)

        # Save results to a file (use linked list moments)
        save_double_pi_values(y1, y2, y3, y4, y5, R1, R2, C1, C2, C3, is_exact)
        print("Results saved to double_pi_values.txt")

        print(f"\nDouble-π model generation completed successfully!")

    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
