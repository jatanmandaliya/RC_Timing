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


# def generate_hspice_file(num_components):
#     with open("rc_network.sp", "w") as f:
#         f.write(".tran 1n 10n\n")
#         f.write(".options post=2 nomod\n")
#         f.write("V1 0 1 DC 1V\n")
#
#         for i in range(1, num_components + 1):
#             if i % 2 == 1:
#                 f.write(f"C{i} {i} {i + 1} 1\n")  # Capacitor in farads
#             else:
#                 f.write(f"R{i} {i} {i + 1} 10\n")  # Resistor in ohms
#         f.write(f".print tran V({num_components + 1})\n")
#         f.write(".end\n")


def parse_hspice_file(filename):
    linked_list = LinkedList()
    with open(filename, "r") as f:
        lines = f.readlines()
        for line in reversed(lines):  # Parse in reverse order
            if line.startswith("R") or line.startswith("C"):
                parts = line.split()
                component_type = parts[0][0]
                value = float(parts[3])  # Value is directly in ohms or farads
                linked_list.append(component_type, value)

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
            YU_3 -= 2 * R * YU_1 * YU_2 + R**2 * (YU_1 ** 3)

        current = current.next

    return YU_1, YU_2, YU_3


def convert_to_pi_model(YU_1, YU_2, YU_3):
    # Calculate total resistance by summing all resistors in the network
   # total_resistance = sum(node.value for node in iterate_linked_list(linked_list) if node.component_type == "R")

    C1 = YU_2 ** 2 / YU_3
    C2 = YU_1 -  ((YU_2 ** 2) / YU_3)
    R1 = -((YU_3 ** 2)/ (YU_2 ** 3))
    return R1, C1, C2


def iterate_linked_list(linked_list):
    """Helper function to iterate over the linked list."""
    current = linked_list.head
    while current:
        yield current
        current = current.next


def save_pi_model_values(YU_1, YU_2, YU_3):
    with open("pi_model_values.txt", "w") as f:
        f.write("Pi Model Values:\n")
        f.write(f"YU1 = {YU_1}\n")
        f.write(f"YU2 = {YU_2}\n")
        f.write(f"YU3 = {YU_3}\n")
        # f.write("\nFinal Component Values:\n")
        # f.write(f"R1 = {R1}\n")
        # f.write(f"C1 = {C1}\n")
        # f.write(f"C2 = {C2}\n")


# Generate HSPICE file for a network with components
#generate_hspice_file(5)

# Parse the HSPICE file into a linked list
linked_list = parse_hspice_file("rc_network.sp")

# Apply rules to calculate upstream traversal values (YU)
YU_1, YU_2, YU_3 = apply_rules(linked_list)

# Convert to π model to find R1, C1, and C2
R1, C1, C2 = convert_to_pi_model(YU_1, YU_2, YU_3)

# Print final results
print("Final Upstream Values:")
print(f"YU_1 = {YU_1}")
print(f"YU_2 = {YU_2}")
print(f"YU_3 = {YU_3}")
#
print("\nFinal Component Values:")
print(f"R1 = {R1}")
print(f"C1 = {C1}")
print(f"C2 = {C2}")

# Save results to a file
#save_pi_model_values(YU_1, YU_2, YU_3, R1, C1, C2)
save_pi_model_values(YU_1, YU_2, YU_3)


# View saved files (optional)
with open("pi_model_values.txt", "r") as f:
    print("\nSaved Pi Model Values File:")
    print(f.read())

with open("rc_network.sp", "r") as a:
    print("\nSaved Pi Model Values File:")
    print(a.read())
