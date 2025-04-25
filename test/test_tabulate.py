from tabulate import tabulate

data = [
    ["Alice", 25, "New York"],
    ["Bob", 30, "London"],
    ["Charlie", 35, "Tokyo"]
]
headers = ["Name", "Age", "City"]

print(tabulate(data, headers=headers, tablefmt="grid"))