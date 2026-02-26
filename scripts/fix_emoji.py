"""
fix_emoji.py - 批量清理代码注释和日志中的 emoji 表情符号

替换规则:
    ->  [FIX]
    ->  [OK]
    ->  [ERROR]
    ->  [WARN]
  📅  ->  (删除，保留后续文字)
  📦  ->  (删除)
  ⏹️  ->  (删除)
    ->  (删除)
    ->  (删除)
  🔍  ->  (删除)
  其余 emoji  ->  (删除)
"""
import os

# emoji -> 替换文本
REPLACEMENTS = [
    ("\U0001F527", "[FIX]"),        # 
    ("\u2705",     "[OK]"),         # 
    ("\u2713",     "[OK]"),         # ✓
    ("\u2714\uFE0F", "[OK]"),       # ✔️
    ("\u2714",     "[OK]"),         # ✔
    ("\u274C",     "[ERROR]"),      # 
    ("\u26A0\uFE0F", "[WARN]"),     # 
    ("\u26A0",     "[WARN]"),       # ⚠
    ("\U0001F504", "[...]"),        # 🔄 reload
    ("\U0001F6D1", "[STOP]"),       # 🛑 stop sign
    ("\U0001F9F9", ""),             # 🧹
    ("\U0001F4E1", ""),             # 📡
    ("\U0001F50C", ""),             # 🔌
    ("\U0001F4CB", ""),             # 📋
    ("\U0001F4CD", ""),             # 📍
    ("\U0001F4CF", ""),             # 📏
    ("\U0001F550", ""),             # 🕐
    ("\U0001F4BE", ""),             # 💾
    ("\U0001F4C5", ""),             # 📅
    ("\U0001F4E6", ""),             # 📦
    ("\u23F9\uFE0F", ""),           # ⏹️
    ("\u23F9",     ""),             # ⏹
    ("\U0001F680", ""),             # 
    ("\U0001F4CA", ""),             # 
    ("\U0001F50D", ""),             # 🔍
    ("\U0001F4DD", ""),             # 
    ("\U0001F4C1", ""),             # 
    ("\U0001F3AF", ""),             # 
    ("\U0001F4A1", ""),             # 
    ("\u2B50",     ""),             # 
    ("\U0001F525", ""),             # 
    ("\U0001F6A7", ""),             # 🚧
    ("\U0001F4AC", ""),             # 💬
    ("\u2139\uFE0F", ""),           # ℹ️
    ("\u2139",     ""),             # ℹ
]

def process_file(path: str) -> tuple[int, list[str]]:
    """处理单个文件，返回 (修改行数, 修改摘要)"""
    with open(path, encoding='utf-8') as f:
        original_lines = f.readlines()

    new_lines = []
    changes = []
    for i, line in enumerate(original_lines, 1):
        new_line = line
        for emoji, replacement in REPLACEMENTS:
            if emoji in new_line:
                new_line = new_line.replace(emoji, replacement)

        if new_line != line:
            changes.append(f"  L{i}: {line.rstrip()[:80]}")

        new_lines.append(new_line)

    if changes:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

    return len(changes), changes


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
    app_dir = os.path.join(base, 'app')

    total_files = 0
    total_changes = 0

    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fname in sorted(files):
            if not fname.endswith('.py'):
                continue
            path = os.path.join(root, fname)
            rel = path.replace(base + os.sep, '').replace(os.sep, '/')
            n, details = process_file(path)
            if n > 0:
                total_files += 1
                total_changes += n
                print(f"[MOD] {rel} ({n} lines changed)")
                for d in details:
                    print(d)

    print(f"\n[DONE] {total_files} files modified, {total_changes} lines changed")


if __name__ == '__main__':
    main()
