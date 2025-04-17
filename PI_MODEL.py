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


def parse_unit_prefix(value_str):
    """Convert SPICE unit prefixes to actual values."""
    unit_prefixes = {
        'f': 1e-15,  # femto
        'p': 1e-12,  # pico
        'n': 1e-9,  # nano
        'u': 1e-6,  # micro
        'm': 1e-3,  # milli
        'k': 1e3,  # kilo
        'meg': 1e6,  # mega
        'g': 1e9,  # giga
    }

    # Handle case where value is already a pure number
    try:
        return float(value_str)
    except ValueError:
        pass

    # Extract the numeric part and unit part
    numeric_part = ""
    unit_part = ""

    for char in value_str:
        if char.isdigit() or char == '.':
            numeric_part += char
        else:
            unit_part = value_str[len(numeric_part):].lower()
            break

    try:
        value = float(numeric_part)
        # Apply unit prefix if exists
        for prefix, multiplier in unit_prefixes.items():
            if unit_part == prefix:
                value *= multiplier
                break
        return value
    except ValueError:
        return None


def parse_hspice_file(filename):
    linked_list = LinkedList()
    rc_components = []

    with open(filename, "r") as f:
        lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith('*') or line.startswith('.'):
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            component_name = parts[0].upper()

            # Check if this is a resistor or capacitor
            if component_name.startswith('R') or component_name.startswith('C'):
                component_type = component_name[0]

                # Find the value - typically the last part, but check for common formats
                value_str = parts[-1]  # Assume value is the last parameter

                # Handle cases where the value might be elsewhere
                for part in parts[3:]:  # Values typically after node definitions
                    if any(char.isdigit() for char in part):
                        value_str = part
                        break

                try:
                    value = parse_unit_prefix(value_str)
                    if value is not None:
                        linked_list.append(component_type, value)
                        rc_components.append(line)  # Store the original line
                except (ValueError, IndexError):
                    pass  # Skip if value cannot be parsed

    return linked_list, rc_components


def find_rc_section(lines):
    """Identify the start and end lines of the RC network section."""
    start_idx = -1
    end_idx = -1
    rc_lines = []
    in_rc_section = False
    rc_component_count = 0

    for i, line in enumerate(lines):
        line = line.strip()

        # Skip comments and empty lines
        if not line or line.startswith('*'):
            continue

        # Check if line starts with R or C
        if (line.startswith('R') or line.startswith('C')) and not line.startswith('.'):
            if not in_rc_section:
                start_idx = i
                in_rc_section = True
            rc_lines.append(line)
            rc_component_count += 1
        elif in_rc_section:
            # Check if we've exited the RC section (encountered a non-RC component)
            # Only consider it the end if we've found at least 2 RC components
            if rc_component_count >= 2 and not (line.startswith('R') or line.startswith('C')):
                end_idx = i
                break

    # If we reached the end of the file still in RC section
    if in_rc_section and end_idx == -1:
        end_idx = len(lines)

    return start_idx, end_idx, rc_lines


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


def get_rc_network_nodes(rc_lines):
    """Extract the start and end nodes of the RC network."""
    if not rc_lines:
        return "1", "2"  # Default if no RC components found

    # Get the first component's first node (start node)
    first_line = rc_lines[0].strip()
    parts = first_line.split()
    if len(parts) >= 3:
        start_node = parts[1]
    else:
        start_node = "1"

    # Find the last node in the sequence
    nodes = set()
    for line in rc_lines:
        parts = line.strip().split()
        if len(parts) >= 3:
            nodes.add(parts[1])
            nodes.add(parts[2])

    # The end node is likely the one that appears only once (at the end of chain)
    node_count = {}
    for line in rc_lines:
        parts = line.strip().split()
        if len(parts) >= 3:
            node_count[parts[1]] = node_count.get(parts[1], 0) + 1
            node_count[parts[2]] = node_count.get(parts[2], 0) + 1

    end_nodes = [node for node, count in node_count.items() if count == 1 and node != start_node]
    if end_nodes:
        end_node = end_nodes[0]
    else:
        # If no clear end node, use the highest numbered node
        numeric_nodes = []
        for node in nodes:
            try:
                numeric_nodes.append((int(node), node))
            except ValueError:
                pass
        if numeric_nodes:
            end_node = max(numeric_nodes)[1]
        else:
            end_node = "2"  # Default end node

    return start_node, end_node


def generate_pi_model_spice_file(input_file, output_file, R1, C1, C2):
    """Generate a new SPICE file with the Pi model replacing the RC network."""
    with open(input_file, "r") as f:
        lines = f.readlines()

    # Find the RC network section
    start_idx, end_idx, rc_lines = find_rc_section(lines)

    if start_idx == -1:
        print("No RC network found in the file.")
        return

    # Get the starting node of the RC network
    start_node, _ = get_rc_network_nodes(rc_lines)

    # Create the new file
    with open(output_file, "w") as f:
        # Write everything before the RC network
        for i in range(start_idx):
            f.write(lines[i])

        # Write Pi model components
        f.write(f"R1 {start_node} 2 {R1:.6g}\n")
        f.write(f"C1 {start_node} 0 {C1:.6g}\n")
        f.write(f"C2 2 0 {C2:.6g}\n")

        # Write everything after the RC network
        for i in range(end_idx, len(lines)):
            f.write(lines[i])


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


def main(input_file, output_file):
    # Parse the HSPICE file into a linked list
    linked_list, rc_components = parse_hspice_file(input_file)

    if not linked_list.head:
        print("No valid RC components found in the file.")
        return

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


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3:
        input_file = sys.argv[1]
        output_file = sys.argv[2]
    else:
        input_file = "rc_network.sp"
        output_file = "rc_network_pi_model.sp"

    main(input_file, output_file)
