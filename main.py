import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime
import config

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', 
                    handlers=[logging.FileHandler("function.log", "w", encoding="utf-8"), logging.StreamHandler()])

def parse_template(template_file):
    """
    解析模板文件，提取频道分类和频道名称。
    
    :param template_file: 模板文件路径
    :return: 包含频道分类和频道名称的OrderedDict
    """
    template_channels = OrderedDict()
    current_category = None

    with open(template_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "#genre#" in line:
                    # 提取当前类别
                    current_category = line.split(",")[0].strip()
                    template_channels[current_category] = []
                elif current_category:
                    # 提取频道名称并加入当前类别中
                    channel_name = line.split(",")[0].strip()
                    template_channels[current_category].append(channel_name)

    return template_channels

# 数据清洗函数
def clean_channel_name(channel_name):
    """
    清洗频道名称，去掉非字母数字字符，保留频道数字部分，并转换为大写。
    
    :param channel_name: 原始频道名称
    :return: 清洗后的频道名称
    """
    cleaned_name = re.sub(r'[$「」-]', '', channel_name)  # 去掉中括号、«», 和'-'字符
    cleaned_name = re.sub(r'\s+', '', cleaned_name)  # 去掉所有空白字符
    cleaned_name = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned_name)  # 将数字前面的部分保留，数字转换为整数
    return cleaned_name.upper()  # 转换为大写

def fetch_channels(url):
    """
    从指定URL抓取频道列表。
    
    :param url: 抓取频道列表的URL
    :return: 包含频道分类和频道信息的OrderedDict
    """
    channels = OrderedDict()

    try:
        response = requests.get(url)
        response.raise_for_status()
        response.encoding = 'utf-8'
        lines = response.text.split("\n")
        current_category = None
        is_m3u = any(line.startswith("#EXTINF") for line in lines[:15])
        source_type = "m3u" if is_m3u else "txt"
        logging.info(f"url: {url} 获取成功，判断为{source_type}格式")

        if is_m3u:
            channels.update(parse_m3u_lines(lines))
        else:
            channels.update(parse_txt_lines(lines))

        if channels:
            categories = ", ".join(channels.keys())
            logging.info(f"url: {url} 成功✅，包含频道分类: {categories}")
    except requests.RequestException as e:
        logging.error(f"url: {url} 失败❌, Error: {e}")

    return channels

def parse_m3u_lines(lines):
    """
    解析M3U格式的频道列表行。
    
    :param lines: M3U格式的频道列表行
    :return: 包含频道分类和频道信息的OrderedDict
    """
    channels = OrderedDict()
    current_category = None

    for line in lines:
        line = line.strip()
        if line.startswith("#EXTINF"):
            match = re.search(r'group-title="(.*?)",(.*)', line)
            if match:
                current_category = match.group(1).strip()
                channel_name = match.group(2).strip()
                if channel_name and channel_name.startswith("CCTV"):  # 判断频道名称是否存在且以CCTV开头
                    channel_name = clean_channel_name(channel_name)  # 频道名称数据清洗

                if current_category not in channels:
                    channels[current_category] = []
        elif line and not line.startswith("#"):
            channel_url = line.strip()
            if current_category and channel_name:
                # 添加频道信息到当前类别中
                channels[current_category].append((channel_name, channel_url))

    return channels

def parse_txt_lines(lines):
    """
    解析TXT格式的频道列表行。
    
    :param lines: TXT格式的频道列表行
    :return: 包含频道分类和频道信息的OrderedDict
    """
    channels = OrderedDict()
    current_category = None

    for line in lines:
        line = line.strip()
        if "#genre#" in line:
            # 提取当前类别
            current_category = line.split(",")[0].strip()
            channels[current_category] = []
        elif current_category:
            match = re.match(r"^(.*?),(.*?)$", line)
            if match:
                channel_name = match.group(1).strip()
                if channel_name and channel_name.startswith("CCTV"):  # 判断频道名称是否存在且以CCTV开头
                    channel_name = clean_channel_name(channel_name)  # 频道名称数据清洗
                # 提取频道URL，并分割成多个部分
                channel_urls = match.group(2).strip().split('#')
            
                # 存储每个分割出的URL
                for channel_url in channel_urls:
                    channel_url = channel_url.strip()  # 去掉前后空白
                    channels[current_category].append((channel_name, channel_url))
            elif line:
                channels[current_category].append((line, ''))

    return channels

def match_channels(template_channels, all_channels):
    """
    匹配模板中的频道与抓取到的频道。
    
    :param template_channels: 模板中的频道分类和频道名称
    :param all_channels: 抓取到的所有频道信息
    :return: 匹配后的频道信息
    """
    matched_channels = OrderedDict()

    for category, channel_list in template_channels.items():
        matched_channels[category] = OrderedDict()
        for channel_name in channel_list:
            for online_category, online_channel_list in all_channels.items():
                for online_channel_name, online_channel_url in online_channel_list:
                    if channel_name == online_channel_name:
                        # 匹配成功的频道信息加入结果中
                        matched_channels[category].setdefault(channel_name, []).append(online_channel_url)

    return matched_channels

def filter_source_urls(template_file):
    """
    过滤源URL，获取匹配后的频道信息。
    
    :param template_file: 模板文件路径
    :return: 匹配后的频道信息和模板中的频道分类及名称
    """
    template_channels = parse_template(template_file)
    source_urls = config.source_urls

    all_channels = OrderedDict()
    for url in source_urls:
        fetched_channels = fetch_channels(url)
        merge_channels(all_channels, fetched_channels)

    matched_channels = match_channels(template_channels, all_channels)

    return matched_channels, template_channels

def merge_channels(target, source):
    """
    合并两个频道字典。
    
    :param target: 目标频道字典
    :param source: 源频道字典
    """
    for category, channel_list in source.items():
        if category in target:
            target[category].extend(channel_list)
        else:
            target[category] = channel_list

def is_ipv6(url):
    """
    判断URL是否为IPv6地址。
    
    :param url: URL字符串
    :return: 如果是IPv6地址返回True，否则返回False
    """
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None

def updateChannelUrlsM3U(channels, template_channels):
    """
    更新频道URL到M3U和TXT文件中。
    
    :param channels: 匹配后的频道信息
    :param template_channels: 模板中的频道分类及名称
    """
    written_urls = set()

    current_date = datetime.now().strftime("%Y-%m-%d")
   # for group in config.announcements:
    #    for announcement in group['entries']:
     #       if announcement['name'] is None:
      #          announcement['name'] = current_date

    with open("live.m3u", "w", encoding="utf-8") as f_m3u:
        f_m3u.write(f"""#EXTM3U x-tvg-url={",".join(f'"{epg_url}"' for epg_url in config.epg_urls)}\n""")

        with open("live.txt", "w", encoding="utf-8") as f_txt:
           # for group in config.announcements:
            #    f_txt.write(f"{group['channel']},#genre#\n")
              #  for announcement in group['entries']:
               #     f_m3u.write(f"""#EXTINF:-1 tvg-id="1" tvg-name="{announcement['name']}" tvg-logo="{announcement['logo']}" group-title="{group['channel']}",{announcement['name']}\n""")
               #     f_m3u.write(f"{announcement['url']}\n")
               #     f_txt.write(f"{announcement['name']},{announcement['url']}\n")

            for category, channel_list in template_channels.items():
                f_txt.write(f"{category},#genre#\n")
                if category in channels:
                    for channel_name in channel_list:
                        if channel_name in channels[category]:
                            sorted_urls = sort_and_filter_urls(channels[category][channel_name], written_urls)
                            total_urls = len(sorted_urls)
                            for index, url in enumerate(sorted_urls, start=1):
                                new_url = add_url_suffix(url, index, total_urls)
                                write_to_files(f_m3u, f_txt, category, channel_name, index, new_url)

            f_txt.write("\n")

def sort_and_filter_urls(urls, written_urls):
    """
    排序和过滤URL。
    
    :param urls: URL列表
    :param written_urls: 已写入的URL集合
    :return: 排序和过滤后的URL列表
    """
    filtered_urls = [
        url for url in sorted(urls, key=lambda u: not is_ipv6(u) if config.ip_version_priority == "ipv6" else is_ipv6(u))
        if url and url not in written_urls and not any(blacklist in url for blacklist in config.url_blacklist)
    ]
    written_urls.update(filtered_urls)
    return filtered_urls

def add_url_suffix(url, index, total_urls):
    """
    添加URL后缀。
    
    :param url: 原始URL
    :param index: URL索引
    :param total_urls: 总URL数量
    :return: 添加后缀后的URL
    """
    if is_ipv6(url):
        suffix = f"$LR•IPV6" if total_urls == 1 else f"$LR•IPV6『线路{index}』"
    else:
        suffix = f"$LR•IPV4" if total_urls == 1 else f"$LR•IPV4『线路{index}』"
    base_url = url.split('$', 1)[0] if '$' in url else url
    return f"{base_url}{suffix}"

def write_to_files(f_m3u, f_txt, category, channel_name, index, new_url):
    """
    写入M3U和TXT文件。
    
    :param f_m3u: M3U文件对象
    :param f_txt: TXT文件对象
    :param category: 频道分类
    :param channel_name: 频道名称
    :param index: URL索引
    :param new_url: 新的URL
    """
    logo_url = f"https://gcore.jsdelivr.net/gh/yuanzl77/TVlogo@master/png/{channel_name}.png"
    f_m3u.write(f"#EXTINF:-1 tvg-id=\"{index}\" tvg-name=\"{channel_name}\" tvg-logo=\"{logo_url}\" group-title=\"{category}\",{channel_name}\n")
    f_m3u.write(new_url + "\n")
    f_txt.write(f"{channel_name},{new_url}\n")

if __name__ == "__main__":
    template_file = "demo.txt"
    channels, template_channels = filter_source_urls(template_file)
    updateChannelUrlsM3U(channels, template_channels)



