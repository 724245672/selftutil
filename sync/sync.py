import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List

import yaml
from colorama import init, Fore, Style

init(autoreset=True)


class Colors:
    HEADER = Fore.CYAN + Style.BRIGHT
    INFO = Fore.BLUE + Style.BRIGHT
    SUCCESS = Fore.GREEN + Style.BRIGHT
    WARNING = Fore.YELLOW + Style.BRIGHT
    ERROR = Fore.RED + Style.BRIGHT
    EXCLUDE = Fore.MAGENTA + Style.BRIGHT
    COPY = Fore.GREEN
    CREATE = Fore.YELLOW
    DELETE = Fore.RED
    STATS = Fore.CYAN
    RESET = Style.RESET_ALL


@dataclass
class ExcludeRule:
    subtree: Path  # 相对 src_base 的路径，"." 表示根目录
    file_patterns: List[re.Pattern]
    folder_patterns: List[re.Pattern]
    file_depth: str = "deep"  # "deep" 或 "shallow"
    folder_depth: str = "deep"  # "deep" 或 "shallow"


@dataclass
class SyncRule:
    src_path: Path
    dst_path: Path
    delete_extra: bool
    exclude: List[ExcludeRule]


@dataclass
class Config:
    dry_run: bool
    rules: List[SyncRule]


# ============================== 辅助函数 ==============================
def load_config(cur_config: str) -> Config:
    if not Path(cur_config).exists():
        raise FileNotFoundError(f"{Colors.ERROR}配置文件未找到: {cur_config}")

    with open(cur_config, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    dry_run = raw.get("dry_run", True)

    rules = []
    for r in raw.get("rules", []):
        src_path = Path(r["src_path"]).resolve()
        dst_path = Path(r["dst_path"]).resolve()
        delete_extra = r.get("delete_extra", False)

        exclude_list = []
        for ex in r.get("exclude", []):
            # 处理 path（允许空或缺失，表示根目录）
            path_str = ex.get("path", ".")
            if isinstance(path_str, str):
                path_str = path_str.strip()
            if not path_str or path_str == "":
                path_str = "."
            subtree = Path(path_str)

            file_patterns = [re.compile(p) for p in ex.get("files", [])]
            folder_patterns = [re.compile(p) for p in ex.get("folders", [])]

            file_depth = ex.get("file_depth", "deep").lower()
            folder_depth = ex.get("folder_depth", "deep").lower()

            exclude_list.append(ExcludeRule(
                subtree=subtree,
                file_patterns=file_patterns,
                folder_patterns=folder_patterns,
                file_depth=file_depth,
                folder_depth=folder_depth,
            ))

        rules.append(SyncRule(
            src_path=src_path,
            dst_path=dst_path,
            delete_extra=delete_extra,
            exclude=exclude_list,
        ))

    return Config(dry_run=dry_run, rules=rules)


def is_in_subtree(rel_path: Path, subtree: Path) -> bool:
    """deep 模式：rel_path 是否在 subtree 子树中（包括 subtree 本身）"""
    try:
        rel_path.relative_to(subtree)
        return True
    except ValueError:
        return False


# ============================== 主同步逻辑 ==============================
def sync_rule(cur_rule: SyncRule, dry_run: bool):
    src_base = cur_rule.src_path
    dst_base = cur_rule.dst_path
    delete_extra = cur_rule.delete_extra
    exclude_rules = cur_rule.exclude

    if not src_base.exists():
        print(f"{Colors.WARNING}【警告】源目录不存在，跳过: {src_base}")
        return

    print(f"\n{Colors.HEADER}{'=' * 30} 处理规则 {'=' * 30}")
    print(f"{Colors.INFO}源目录: {src_base}")
    print(f"{Colors.INFO}目标目录: {dst_base}")
    print(f"{Colors.INFO}删除多余: {delete_extra}")
    print(
        f"{Colors.INFO}模式: {Colors.WARNING if dry_run else Colors.SUCCESS}{'DRY RUN（仅预览）' if dry_run else '真实执行'}")

    # ---------- 排除判断函数 ----------
    def is_file_excluded(cur_rel_file: Path) -> bool:
        dir_rel = cur_rel_file.parent
        name = cur_rel_file.name
        for r in exclude_rules:
            if not r.file_patterns:
                continue
            # 判断规则是否适用于当前目录
            if r.file_depth == "deep":
                applicable = is_in_subtree(dir_rel, r.subtree)
            else:  # shallow
                applicable = (dir_rel == r.subtree)
            if applicable:
                for pat in r.file_patterns:
                    if pat.search(name):
                        return True
        return False

    def is_folder_excluded(rel_parent: Path, folder_name: str) -> bool:
        for r in exclude_rules:
            if not r.folder_patterns:
                continue
            # 判断规则是否适用于当前父目录
            if r.folder_depth == "deep":
                applicable = is_in_subtree(rel_parent, r.subtree)
            else:  # shallow
                applicable = (rel_parent == r.subtree)
            if applicable:
                for pat in r.folder_patterns:
                    if pat.search(folder_name):
                        return True
        return False

    # ---------- 统计计数器 ----------
    stats = {
        "created_dirs": 0,
        "copied_files": 0,
        "excluded_files": 0,
        "excluded_folders": 0,
        "deleted_files": 0,
        "deleted_dirs": 0,
        "deleted_empty_dirs": 0,
    }

    # ---------- 第一阶段：复制（带排除） ----------
    print(f"\n{Colors.HEADER}【复制阶段】")
    for root, dirs, files in os.walk(src_base, topdown=True):
        root_path = Path(root)
        rel_root = root_path.relative_to(src_base)
        dst_root = dst_base / rel_root

        if not dst_root.exists():
            print(f"{Colors.CREATE}创建文件夹 → {dst_root}")
            stats["created_dirs"] += 1
            if not dry_run:
                dst_root.mkdir(parents=True, exist_ok=True)

        new_dirs = [d for d in dirs if not is_folder_excluded(rel_root, d)]
        excluded_dirs = len(dirs) - len(new_dirs)
        stats["excluded_folders"] += excluded_dirs
        for d in set(dirs) - set(new_dirs):
            print(f"{Colors.EXCLUDE}排除的文件夹 → {rel_root / d}")
        dirs[:] = new_dirs

        for f in files:
            src_file = root_path / f
            rel_file = rel_root / f
            dst_file = dst_base / rel_file

            if is_file_excluded(rel_file):
                print(f"{Colors.EXCLUDE}排除的文件 → {rel_file}")
                stats["excluded_files"] += 1
                continue

            need_copy = True
            if dst_file.exists():
                src_stat = src_file.stat()
                dst_stat = dst_file.stat()
                if src_stat.st_size == dst_stat.st_size and src_stat.st_mtime <= dst_stat.st_mtime + 1:
                    need_copy = False

            if need_copy:
                print(f"{Colors.COPY}更新 → {rel_file}")
                stats["copied_files"] += 1
                if not dry_run:
                    shutil.copy2(src_file, dst_file)

    # ---------- 第二阶段：删除多余 ----------
    if delete_extra:
        print(f"\n{Colors.HEADER}【删除多余阶段】")
        for root, dirs, files in os.walk(dst_base, topdown=False):
            root_path = Path(root)
            rel_root = root_path.relative_to(dst_base)
            src_correspond = src_base / rel_root

            for f in files:
                dst_file = root_path / f
                rel_file = rel_root / f
                src_file = src_correspond / f

                if not src_file.exists() or is_file_excluded(rel_file):
                    print(f"{Colors.DELETE}删除文件 → {dst_file}")
                    stats["deleted_files"] += 1
                    if not dry_run:
                        dst_file.unlink()

            for d in dirs[:]:
                dst_dir = root_path / d
                src_dir = src_correspond / d

                if not src_dir.exists() or is_folder_excluded(rel_root, d):
                    if dst_dir.exists():
                        print(f"{Colors.DELETE}删除文件夹 → {dst_dir}")
                        stats["deleted_dirs"] += 1
                        if not dry_run:
                            shutil.rmtree(dst_dir) if any(dst_dir.iterdir()) else dst_dir.rmdir()

            if not src_correspond.exists() and root_path.exists() and not any(root_path.iterdir()):
                print(f"{Colors.DELETE}删除空文件夹 → {root_path}")
                stats["deleted_empty_dirs"] += 1
                if not dry_run:
                    root_path.rmdir()

    # ---------- 统计总结 ----------
    print(f"\n{Colors.HEADER}{'-' * 30} 本规则统计总结 {'-' * 30}")
    print(f"{Colors.STATS}新建目录      : {stats['created_dirs']}")
    print(f"{Colors.STATS}复制文件      : {stats['copied_files']}")
    print(f"{Colors.STATS}排除文件      : {stats['excluded_files']}")
    print(f"{Colors.STATS}排除文件夹    : {stats['excluded_folders']}")
    if delete_extra:
        print(f"{Colors.STATS}删除文件      : {stats['deleted_files']}")
        total_deleted_dirs = stats['deleted_dirs'] + stats['deleted_empty_dirs']
        print(f"{Colors.STATS}删除目录      : {total_deleted_dirs}")
        print(f"{Colors.STATS}（其中空目录删除: {stats['deleted_empty_dirs']}）")
    print(f"{Colors.HEADER}{'-' * 70}")


# ============================== 主程序 ==============================
if __name__ == "__main__":
    try:
        config = load_config("config.yaml")

        for i, rule in enumerate(config.rules, 1):
            print(f"\n{Colors.HEADER}{'*' * 80}")
            print(f"{Colors.HEADER}开始处理第 {i} 条规则")
            sync_rule(rule, config.dry_run)

        print(f"\n{Colors.SUCCESS}{'=' * 30} 全部规则处理完成 {'=' * 30}")
    except Exception as e:
        print(f"{Colors.ERROR}错误: {e}")
        import traceback

        traceback.print_exc()
