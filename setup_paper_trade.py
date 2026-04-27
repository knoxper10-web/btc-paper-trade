# File: setup_paper_trade.py
import json
from datetime import datetime

def setup_initial_config():
    """初期設定ファイルの作成"""
    config = {
        "monthly_budget": 1000,
        "initial_btc": 0,
        "initial_cash": 10000,
        "fee": 0.001,
        "buy_threshold_low": 2.5,
        "buy_threshold_mid": 3.5,
        "buy_threshold_high": 4.5,
        "sell_threshold": 4.0,
        "sell_ratio": 0.05,
        "cooldown_days": 14,
        "start_date": datetime.now().strftime("%Y-%m-%d")
    }
    
    with open('paper_trade_config.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print("設定ファイル 'paper_trade_config.json' を作成しました")
    print("\n設定内容:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    print("\n✅ セットアップ完了！")
    print("📌 使い方:")
    print("  1. 日次実行: python btc_paper_trade.py")
    print("  2. 分析レポート: python paper_trade_analyzer.py")

if __name__ == "__main__":
    setup_initial_config()