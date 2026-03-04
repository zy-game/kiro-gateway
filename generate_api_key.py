#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速生成 API Key 的脚本
"""

from kiro.core.auth import AccountManager

def main():
    print("=" * 60)
    print("Kiro Gateway - API Key 生成工具")
    print("=" * 60)
    
    # 初始化 AccountManager
    am = AccountManager()
    
    # 列出现有的 API Keys
    existing_keys = am.list_api_keys()
    print(f"\n当前已有 {len(existing_keys)} 个 API Key:")
    for key in existing_keys:
        print(f"  - {key.name}: {key.key}")
    
    # 生成新的 API Key
    print("\n正在生成新的 API Key...")
    new_key = am.generate_api_key("Auto-generated Key")
    
    print("\n✅ API Key 生成成功！")
    print("=" * 60)
    print(f"名称: {new_key.name}")
    print(f"Key:  {new_key.key}")
    print("=" * 60)
    print("\n⚠️  请妥善保存此 Key，它只会显示一次！")
    print("\n使用方法:")
    print("  Anthropic 格式: -H 'x-api-key: {}'".format(new_key.key))
    print("  OpenAI 格式:    -H 'Authorization: Bearer {}'".format(new_key.key))
    print()

if __name__ == "__main__":
    main()
