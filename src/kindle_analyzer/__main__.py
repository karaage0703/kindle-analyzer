"""Kindleの蔵書情報を分析するためのエントリーポイント。

このモジュールは、`python -m kindle_analyzer`コマンドで実行されるエントリーポイントです。
"""

from .cli import main

if __name__ == "__main__":
    main()
