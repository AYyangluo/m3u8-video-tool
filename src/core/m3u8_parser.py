import re
from urllib.parse import urljoin

import requests

from src.utils.config import Config


class M3U8Parser:
    """m3u8 解析器，用于解析m3u8播放列表并提取ts片段链接。"""

    def __init__(self):
        """初始化解析器，创建复用连接的请求会话。"""
        # 复用连接的请求会话，并带上默认请求头
        self.session = requests.Session()
        self.session.headers.update(Config.DEFAULT_HEADERS)

    def parse(self, url):
        """解析m3u8链接，返回包含片段、变体、时长等信息的字典。

        Args:
            url: m3u8 文件的URL

        Returns:
            dict: 包含以下字段：
                - segments: ts片段URL列表
                - is_master: 是否为主播放列表（多码率）
                - variants: 各码率变体信息列表
                - duration: 总时长（秒），可计算时返回
        """
        content = self._fetch(url)
        return self.parse_content(content, url)

    def parse_content(self, content, base_url):
        """解析m3u8文本内容，返回结构化信息。

        Args:
            content: m3u8 文件的文本内容
            base_url: 基础URL，用于将相对路径拼接为完整URL

        Returns:
            dict: 解析结果，字段同 parse 方法
        """
        result = {
            "segments": [],
            "is_master": False,
            "variants": [],
            "duration": 0.0,
        }

        # 非法内容或缺少文件头直接返回空结果
        if not content or "#EXTM3U" not in content:
            return result

        lines = content.splitlines()
        is_master = False
        variants = []
        segments = []
        total_duration = 0.0
        # 暂存 #EXT-X-STREAM-INF 解析出的变体属性，等待下一行URL
        pending_variant = None

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            # 主播放列表变体声明
            if line.startswith("#EXT-X-STREAM-INF"):
                is_master = True
                attrs = self._parse_attributes(line)
                try:
                    bandwidth = int(attrs.get("BANDWIDTH", "0") or "0")
                except ValueError:
                    bandwidth = 0
                pending_variant = {
                    "url": "",
                    "bandwidth": bandwidth,
                    "resolution": attrs.get("RESOLUTION", ""),
                    "codecs": attrs.get("CODECS", ""),
                }
                continue

            # 片段信息：#EXTINF:<duration>,<title>
            if line.startswith("#EXTINF"):
                duration = self._parse_extinf_duration(line)
                if duration > 0:
                    total_duration += duration
                continue

            # 结束标记，无需特殊处理
            if line.startswith("#EXT-X-ENDLIST"):
                continue

            # 其他注释行直接跳过
            if line.startswith("#"):
                continue

            # 非#开头的行即为URL（片段或变体），拼接为绝对URL
            full_url = urljoin(base_url, line)

            if is_master and pending_variant is not None:
                # 变体URL行
                pending_variant["url"] = full_url
                variants.append(pending_variant)
                pending_variant = None
            elif is_master:
                # 缺少STREAM-INF声明的变体URL，简单记录
                variants.append({"url": full_url, "bandwidth": 0})
            else:
                # 媒体播放列表的ts片段
                segments.append(full_url)

        result["is_master"] = is_master
        result["variants"] = variants
        result["segments"] = segments
        result["duration"] = total_duration

        # 若为主播放列表，自动选择最高码率变体并递归解析
        if is_master and variants:
            best_variant = self._select_best_variant(variants)
            if best_variant and best_variant.get("url"):
                try:
                    sub_result = self.parse(best_variant["url"])
                    # 用子播放列表的片段与时长覆盖当前结果
                    result["segments"] = sub_result.get("segments", [])
                    result["duration"] = sub_result.get("duration", total_duration)
                except Exception:
                    # 子解析失败时保留主播放列表原始结构
                    pass

        return result

    def _fetch(self, url):
        """下载m3u8文本内容。"""
        response = self.session.get(url, timeout=Config.DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _parse_extinf_duration(line):
        """从 #EXTINF 行中解析片段时长。"""
        try:
            # 形如 #EXTINF:10.000,标题 或 #EXTINF:10.000
            value_part = line.split(":", 1)[1]
            duration_str = value_part.split(",")[0].strip()
            return float(duration_str)
        except (IndexError, ValueError):
            return 0.0

    @staticmethod
    def _parse_attributes(line):
        """解析标签中的属性键值对，如 BANDWIDTH=1280000,RESOLUTION="1280x720"。"""
        attrs = {}
        if ":" not in line:
            return attrs
        attr_str = line.split(":", 1)[1]
        # 匹配 KEY="VALUE" 或 KEY=VALUE 两种形式
        pattern = re.compile(r'([A-Z0-9-]+)=("([^"]*)"|([^,]+))')
        for match in pattern.finditer(attr_str):
            key = match.group(1)
            # 优先取带引号的内部值，否则取无引号的值
            value = match.group(3) if match.group(3) is not None else match.group(4)
            attrs[key] = value.strip() if value else ""
        return attrs

    @staticmethod
    def _select_best_variant(variants):
        """选择最高码率变体；若无码率信息则取第一个。"""
        if not variants:
            return None
        has_bandwidth = any(v.get("bandwidth", 0) for v in variants)
        if has_bandwidth:
            return max(variants, key=lambda v: v.get("bandwidth", 0))
        return variants[0]
