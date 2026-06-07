#!/usr/bin/env python3
"""
solve.py for demo_table_001
计算 North 区域的总 revenue
"""

import pandas as pd
import json
import os

def main():
    # 读取数据文件
    data_file = "data.csv"
    if not os.path.exists(data_file):
        raise FileNotFoundError(f"数据文件 {data_file} 不存在")
    
    # 读取CSV文件
    df = pd.read_csv(data_file)
    
    # 确保revenue列是数值类型
    df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')
    
    # 过滤North区域的数据
    north_data = df[df['region'] == 'North']
    
    # 计算North区域的总revenue
    total_revenue = north_data['revenue'].sum()
    
    # 创建结果字典
    result = {
        "total_revenue": float(total_revenue)
    }
    
    # 输出answer.json
    with open('answer.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"North区域的总revenue: {total_revenue}")
    print("结果已保存到 answer.json")

if __name__ == "__main__":
    main()