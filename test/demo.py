from tabulate import tabulate

data = [
    ["Alice", 25, "New York"],
    ["Bob", 30, "London"],
    ["Charlie", 35, "Tokyo"]
]
headers = ["Name", "Age", "City"]

# 输出纯文本表格（类似淘宝的 TableElement）
print(tabulate(data, headers=headers, tablefmt="grid"))