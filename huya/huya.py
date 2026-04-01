import base64
import hashlib
import json
import os
import random
import subprocess
import sys
import time
import urllib.parse

import requests
from PySide6.QtCore import Qt, QThread, Signal, QSize, QThreadPool, QRunnable, QObject, Slot
from PySide6.QtGui import QPixmap, QBrush, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QGroupBox,
    QGridLayout, QMessageBox, QListWidget, QListWidgetItem,
    QSplitter, QMenu, QTreeWidget, QTreeWidgetItem
)
from bs4 import BeautifulSoup


class Huya:
    HUYA_URL = "https://www.huya.com"
    LIST_URL = "https://live.huya.com/liveHttpUI/getLiveList?iGid={gid}&iPageNo={page}&iPageSize=120"
    SEARCH_URL = "https://www.huya.com/search"
    CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                 "Chrome/140.0.0.0 Safari/537.36")

    CONSTANTS = {
        "t": "100",
        "ver": "1",
        "sv": "2401090219",
        "codec": "264"
    }

    STREAM_URL_QUERYSTRING_PARAMS = {"wsTime", "fm", "ctype", "fs"}

    MAIN_CATEGORIES = {
        "网游竞技": "1",
        "手游休闲": "8",
        "单机热游": "2",
        "娱乐星秀": "3",
    }

    SUB_CATEGORIES_DATA = {
        "网游竞技": {"g_ol": [{"n": "英雄联盟", "v": "1"}, {"n": "CS2", "v": "862"}, {"n": "无畏契约", "v": "5937"},
                              {"n": "lol云顶之弈", "v": "5485"}, {"n": "穿越火线", "v": "4"},
                              {"n": "炉石传说", "v": "393"}, {"n": "逆战", "v": "135"}, {"n": "DOTA2", "v": "7"},
                              {"n": "DOTA1", "v": "6"}, {"n": "地下城与勇士", "v": "2"},
                              {"n": "魔兽争霸3", "v": "4615"}, {"n": "坦克世界", "v": "802"},
                              {"n": "网游竞技", "v": "100023"}, {"n": "射击综合游戏", "v": "100141"},
                              {"n": "暴雪专区", "v": "100043"}, {"n": "棋牌休闲", "v": "100301"},
                              {"n": "冒险岛", "v": "2243"}, {"n": "传奇", "v": "983"}, {"n": "桌游", "v": "100305"},
                              {"n": "剑灵", "v": "897"}, {"n": "魔兽世界", "v": "8"}, {"n": "诛仙3", "v": "1646"},
                              {"n": "军事游戏", "v": "100133"}, {"n": "和平精英模拟器", "v": "71827"},
                              {"n": "QQ飞车", "v": "9"}, {"n": "热血江湖", "v": "387"}, {"n": "英魂之刃", "v": "1830"},
                              {"n": "彩虹岛Online", "v": "683"}, {"n": "起凡：群雄逐鹿", "v": "1612"},
                              {"n": "问道", "v": "107"}, {"n": "燕云十六声", "v": "8019"}, {"n": "梦三国", "v": "489"},
                              {"n": "暗黑破坏神", "v": "1123"}, {"n": "守望先锋", "v": "2174"},
                              {"n": "武林外传一世琴缘", "v": "1661"}, {"n": "命运方舟", "v": "3058"},
                              {"n": "剑网3", "v": "900"}, {"n": "丝路传说2", "v": "1026"},
                              {"n": "全面战争：竞技场", "v": "5901"}, {"n": "新飞飞(FlyFF)", "v": "1582"},
                              {"n": "炉石战棋", "v": "5751"}, {"n": "黑色沙漠", "v": "1877"},
                              {"n": "夺宝传世", "v": "772"}, {"n": "CFHD", "v": "6079"}, {"n": "QQ华夏", "v": "1878"},
                              {"n": "流放之路", "v": "427"}, {"n": "暗区突围：无限", "v": "10963"},
                              {"n": "FF14", "v": "1111"}, {"n": "战舰世界", "v": "1947"}, {"n": "逆水寒", "v": "2952"},
                              {"n": "星际争霸", "v": "5"}, {"n": "体育游戏", "v": "100135"},
                              {"n": "天翼决", "v": "779"}, {"n": "九阴真经", "v": "1009"}, {"n": "寻仙", "v": "734"},
                              {"n": "反恐精英Online", "v": "1918"}, {"n": "斗战神", "v": "591"},
                              {"n": "新天龙八部", "v": "5671"}, {"n": "使命召唤：战区", "v": "5911"},
                              {"n": "全球使命3", "v": "2953"}, {"n": "格斗游戏", "v": "100299"},
                              {"n": "神武4电脑版", "v": "3227"}, {"n": "天谕", "v": "1899"},
                              {"n": "生死狙击", "v": "2471"}, {"n": "征途", "v": "2715"},
                              {"n": "生死狙击2", "v": "6091"}, {"n": "天堂", "v": "1966"},
                              {"n": "诛仙世界", "v": "7749"}, {"n": "反恐行动online", "v": "861"},
                              {"n": "虎牙全明星", "v": "65907"}, {"n": "梦幻诛仙2", "v": "488"},
                              {"n": "仙剑世界", "v": "8275"}, {"n": "完美世界：诸神之战", "v": "7217"},
                              {"n": "泡泡堂", "v": "440"}, {"n": "QQ仙侠传", "v": "2291"}, {"n": "KARDS", "v": "8261"},
                              {"n": "神泣", "v": "2531"}, {"n": "NBA2KOL系列", "v": "3959"},
                              {"n": "漫威争锋", "v": "11051"}, {"n": "领地人生", "v": "2282"},
                              {"n": "无限法则", "v": "3189"}, {"n": "御龙在天", "v": "675"},
                              {"n": "魅力飞飞", "v": "2915"}, {"n": "刀剑英雄", "v": "915"}, {"n": "激战2", "v": "406"},
                              {"n": "征途2", "v": "677"}, {"n": "凡人修仙传Online", "v": "920"},
                              {"n": "命运扳机", "v": "73095"}, {"n": "QQ三国", "v": "1090"},
                              {"n": "忍者村大战2", "v": "2369"}, {"n": "全境封锁2", "v": "5023"},
                              {"n": "全球使命", "v": "939"}]},
        "单机热游": {"g_pc": [{"n": "天天吃鸡", "v": "2793"}, {"n": "主机游戏", "v": "100032"},
                              {"n": "黑神话：悟空", "v": "6111"}, {"n": "我的世界", "v": "1732"},
                              {"n": "方舟", "v": "1997"}, {"n": "逃离塔科夫", "v": "3493"},
                              {"n": "单机热游", "v": "100002"}, {"n": "互动点播", "v": "5907"},
                              {"n": "无主星渊", "v": "74273"}, {"n": "永劫无间", "v": "6219"},
                              {"n": "怀旧游戏", "v": "100125"}, {"n": "流放之路：降临", "v": "73759"},
                              {"n": "部落：上升", "v": "1318"}, {"n": "鹅鸭杀", "v": "6101"},
                              {"n": "恐怖游戏", "v": "9453"}, {"n": "互动剧游", "v": "6919"},
                              {"n": "Dread Hunger", "v": "7601"}, {"n": "怪物猎人：崛起", "v": "6479"},
                              {"n": "怪物猎人物语", "v": "7101"}, {"n": "罗布乐思", "v": "5771"},
                              {"n": "Among Us", "v": "6163"}, {"n": "不祥之夜：回魂", "v": "10821"},
                              {"n": "森林之子", "v": "7943"}, {"n": "艾尔登法环", "v": "5801"},
                              {"n": "无烬战争", "v": "71831"}, {"n": "育碧游戏", "v": "100139"},
                              {"n": "骑马与砍杀系列", "v": "4783"}, {"n": "饥荒", "v": "74"},
                              {"n": "天国：拯救2", "v": "69105"}, {"n": "完蛋！我被美女包围了！", "v": "10199"},
                              {"n": "怪物猎人：荒野", "v": "69017"}, {"n": "无人深空", "v": "2566"},
                              {"n": "卧龙：苍天陨落", "v": "7859"}, {"n": "海贼王 寻秘世界", "v": "5097"},
                              {"n": "刺客信条", "v": "1962"}, {"n": "鬼谷八荒", "v": "6571"},
                              {"n": "漫威蜘蛛侠", "v": "4249"}, {"n": "全面战争", "v": "3521"},
                              {"n": "只狼：影逝二度", "v": "4505"}, {"n": "失控进化-rust", "v": "70953"},
                              {"n": "霍格沃茨之遗", "v": "7881"}, {"n": "植物大战僵尸", "v": "485"},
                              {"n": "星球大战系列", "v": "554"}, {"n": "战神：诸神黄昏", "v": "7771"},
                              {"n": "DayZ独立版", "v": "1125"}, {"n": "仁王2", "v": "5795"}, {"n": "星空", "v": "7857"},
                              {"n": "甜蜜之家", "v": "6739"}, {"n": "反转21克", "v": "10013"},
                              {"n": "盗贼之海", "v": "3641"}, {"n": "冰汽时代2", "v": "62603"},
                              {"n": "欧洲卡车模拟", "v": "475"}, {"n": "刺客信条：英灵殿", "v": "6149"},
                              {"n": "橙光阅读器", "v": "73363"}, {"n": "Dark and Darker", "v": "7905"},
                              {"n": "极限竞速：地平线", "v": "2634"}, {"n": "双影奇境", "v": "70355"},
                              {"n": "过山车之星", "v": "2853"}, {"n": "塞尔达传说：王国之泪", "v": "7883"},
                              {"n": "双人成行", "v": "6737"}, {"n": "无主之地4", "v": "74059"},
                              {"n": "俄罗斯钓鱼4", "v": "5495"}, {"n": "Apex英雄", "v": "5011"},
                              {"n": "糖豆人：终极淘汰赛", "v": "6083"}, {"n": "原子之心", "v": "7925"},
                              {"n": "拳皇15", "v": "7609"}, {"n": "消逝的光芒2", "v": "7581"},
                              {"n": "音乐游戏", "v": "2761"}, {"n": "港诡实录", "v": "5853"},
                              {"n": "渡神记", "v": "6231"}, {"n": "中国式网游", "v": "10919"},
                              {"n": "猎杀：对决", "v": "3677"}, {"n": "博德之门3", "v": "6147"},
                              {"n": "战锤40K：暗潮", "v": "3016"}, {"n": "荒野大镖客2", "v": "4319"},
                              {"n": "界外狂潮", "v": "68167"}, {"n": "彩虹六号", "v": "2327"},
                              {"n": "最终幻想7：重制版", "v": "5809"}, {"n": "马里奥赛车8", "v": "5947"},
                              {"n": "霓虹深渊", "v": "5743"}, {"n": "荒岛求生", "v": "1907"},
                              {"n": "英灵神殿", "v": "6609"}, {"n": "雾影猎人", "v": "74169"},
                              {"n": "纸人", "v": "5257"}, {"n": "泡姆泡姆", "v": "72501"},
                              {"n": "石油骚动", "v": "2585"}, {"n": "禁闭求生", "v": "6065"},
                              {"n": "杀戮尖塔", "v": "3601"}, {"n": "沉浮", "v": "6845"},
                              {"n": "Steamcraft", "v": "5243"}, {"n": "幽灵行动：荒野", "v": "2794"},
                              {"n": "恶魔之魂", "v": "6151"}, {"n": "忍者龙剑传", "v": "6957"},
                              {"n": "英勇之地", "v": "10593"}, {"n": "环世界", "v": "4865"},
                              {"n": "三国群英传7", "v": "1049"}, {"n": "最终幻想16", "v": "7869"},
                              {"n": "对马岛之魂", "v": "6039"}, {"n": "幻兽帕鲁", "v": "9961"},
                              {"n": "看门狗：军团", "v": "6155"}, {"n": "人类一败涂地", "v": "3289"},
                              {"n": "鬼影缠身", "v": "65"}, {"n": "最终幻想：起源", "v": "7653"},
                              {"n": "PPSSPP模拟器", "v": "1804"}, {"n": "矩阵：零日危机", "v": "70261"},
                              {"n": "真实世界赛车", "v": "1149"}, {"n": "哈迪斯", "v": "6153"},
                              {"n": "星露谷物语", "v": "2443"}, {"n": "碧蓝幻想：Versus", "v": "5869"},
                              {"n": "幽灵线：东京", "v": "7669"}, {"n": "四海兄弟", "v": "5995"},
                              {"n": "恐惧之间", "v": "6679"}, {"n": "仙剑奇侠传七", "v": "6509"},
                              {"n": "怪物猎人世界", "v": "3519"}, {"n": "洛克王国", "v": "2864"},
                              {"n": "瑞奇与叮当", "v": "2455"}, {"n": "SCUM", "v": "4245"},
                              {"n": "恐鬼症", "v": "6205"}, {"n": "猛兽派对", "v": "6165"}, {"n": "边境", "v": "4779"},
                              {"n": "极品飞车系列", "v": "1307"}, {"n": "足球小将", "v": "6103"},
                              {"n": "剑星", "v": "10567"}, {"n": "都市：天际线", "v": "2201"}]},
        "娱乐星秀": {"g_yl": [{"n": "户外", "v": "2165"}, {"n": "星秀", "v": "1663"}, {"n": "原创", "v": "6861"},
                              {"n": "体育", "v": "2356"}, {"n": "一起看", "v": "2135"}, {"n": "交友", "v": "4079"},
                              {"n": "二次元", "v": "2633"}, {"n": "颜值", "v": "2168"}, {"n": "娱乐", "v": "100022"},
                              {"n": "一起玩", "v": "6613"}, {"n": "互动组队", "v": "5367"},
                              {"n": "吃喝玩乐", "v": "100044"}, {"n": "虎牙文化", "v": "4089"},
                              {"n": "音乐", "v": "3793"}, {"n": "科技", "v": "2408"}, {"n": "虚拟偶像", "v": "6055"},
                              {"n": "旅游", "v": "6791"}, {"n": "趣分享", "v": "5883"}, {"n": "一起买", "v": "7759"}]},
        "手游休闲": {"g_sy": [{"n": "王者荣耀", "v": "2336"}, {"n": "无畏契约：源能行动", "v": "62639"},
                              {"n": "三角洲行动", "v": "9449"}, {"n": "和平精英", "v": "3203"},
                              {"n": "金铲铲之战", "v": "7185"}, {"n": "王者模拟战", "v": "5699"},
                              {"n": "综合手游", "v": "100029"}, {"n": "三国杀", "v": "1669"},
                              {"n": "新游广场", "v": "100052"}, {"n": "英雄联盟手游", "v": "6203"},
                              {"n": "火影忍者手游", "v": "2429"}, {"n": "逆水寒手游", "v": "7725"},
                              {"n": "DNF手游", "v": "4921"}, {"n": "CF手游", "v": "2413"},
                              {"n": "QQ飞车手游", "v": "2928"}, {"n": "手游休闲", "v": "100004"},
                              {"n": "摸了个鱼", "v": "9283"}, {"n": "MMORPG", "v": "100273"},
                              {"n": "动作游戏", "v": "100197"}, {"n": "魔兽弧光大作战", "v": "9455"},
                              {"n": "二次元手游", "v": "100091"}, {"n": "幻塔", "v": "6437"},
                              {"n": "欢乐麻将", "v": "1751"}, {"n": "原神", "v": "5489"},
                              {"n": "英雄联盟电竞经理", "v": "7177"}, {"n": "狼人杀手游", "v": "100049"},
                              {"n": "中国象棋", "v": "1671"}, {"n": "天天象棋", "v": "4997"},
                              {"n": "欢乐斗地主", "v": "1749"}, {"n": "永劫无间手游", "v": "7579"},
                              {"n": "新天龙八部手游", "v": "6945"}, {"n": "天天狼人", "v": "2774"},
                              {"n": "虎牙领主争霸", "v": "7529"}, {"n": "SKY光遇", "v": "3719"},
                              {"n": "JJ斗地主", "v": "3841"}, {"n": "暗区突围", "v": "7209"},
                              {"n": "迷你世界", "v": "2683"}, {"n": "决胜巅峰", "v": "7537"},
                              {"n": "荣耀远征", "v": "9385"}, {"n": "元梦之星", "v": "9521"},
                              {"n": "暗黑破坏神：不朽", "v": "6385"}, {"n": "武侠乂手游", "v": "4929"},
                              {"n": "失落之魂", "v": "6053"}, {"n": "武林外传手游", "v": "3331"},
                              {"n": "问道手游", "v": "2477"}, {"n": "斗罗大陆：魂师对决", "v": "6745"},
                              {"n": "塔瑞斯·世界", "v": "7915"}, {"n": "掼蛋", "v": "6225"},
                              {"n": "热血江湖手游", "v": "2817"}, {"n": "忍者必须死3", "v": "4041"},
                              {"n": "狼人杀", "v": "2785"}, {"n": "完美世界手游", "v": "4237"},
                              {"n": "阴阳师", "v": "2598"}, {"n": "御龙在天手游", "v": "2568"},
                              {"n": "三国志战略版", "v": "5619"}, {"n": "妄想山海", "v": "6007"},
                              {"n": "战争冲突", "v": "7449"}, {"n": "军棋", "v": "2561"}, {"n": "风云", "v": "3061"},
                              {"n": "率土之滨", "v": "2691"}, {"n": "雀魂麻将", "v": "7107"},
                              {"n": "魔力宝贝", "v": "2891"}, {"n": "神域纪元", "v": "10943"},
                              {"n": "蛋仔派对", "v": "6909"}, {"n": "崩坏：星穹铁道", "v": "7349"},
                              {"n": "明末：渊虚之羽", "v": "7363"}, {"n": "英雄杀", "v": "2688"},
                              {"n": "部落冲突", "v": "1797"}, {"n": "绝区零", "v": "7711"},
                              {"n": "跑跑卡丁车手游", "v": "2620"}, {"n": "新剑侠情缘手游", "v": "6259"},
                              {"n": "诛仙手游", "v": "2647"}, {"n": "COD手游", "v": "4769"},
                              {"n": "实况足球", "v": "3741"}, {"n": "三国志异闻录", "v": "64259"},
                              {"n": "鸣潮", "v": "8037"}, {"n": "狼人杀官方", "v": "3679"},
                              {"n": "第五人格", "v": "3115"}, {"n": "倩女幽魂手游", "v": "2503"},
                              {"n": "洛克王国：世界", "v": "11043"}, {"n": "指尖四川麻将", "v": "7215"},
                              {"n": "天涯明月刀-赛季版", "v": "5115"}, {"n": "极品飞车：集结", "v": "9421"},
                              {"n": "诸神竞技场", "v": "69373"}, {"n": "斗罗大陆：猎魂世界", "v": "11061"},
                              {"n": "远光84", "v": "9457"}, {"n": "摩尔庄园", "v": "5981"},
                              {"n": "异人之下", "v": "68127"}, {"n": "新笑傲江湖", "v": "5669"},
                              {"n": "奇迹MU：觉醒", "v": "3116"}, {"n": "寻仙手游", "v": "2979"},
                              {"n": "创造与魔法", "v": "2931"}, {"n": "剑灵2", "v": "7223"},
                              {"n": "冒险岛：枫之传说", "v": "8005"}, {"n": "群星纪元", "v": "66203"},
                              {"n": "荒野行动", "v": "3084"}, {"n": "航海王：燃烧意志", "v": "3943"},
                              {"n": "天天吃鸡手机版", "v": "4341"}, {"n": "英勇之地手游", "v": "72299"},
                              {"n": "Binary God", "v": "7039"}, {"n": "饥困荒野", "v": "6491"},
                              {"n": "合金弹头反击", "v": "3965"}, {"n": "天天富翁", "v": "1709"},
                              {"n": "凡人修仙传：人界篇", "v": "8297"}, {"n": "荒野乱斗", "v": "4613"},
                              {"n": "皇帝成长计划2", "v": "6755"}, {"n": "哈利波特：魔法觉醒", "v": "5835"},
                              {"n": "航海王壮志雄心", "v": "10619"}, {"n": "口袋觉醒", "v": "5953"},
                              {"n": "多多自走棋", "v": "5133"}, {"n": "新游推荐", "v": "3160"},
                              {"n": "神将三国", "v": "6621"}, {"n": "明日方舟", "v": "4925"},
                              {"n": "明日方舟：终末地", "v": "8363"}, {"n": "遮天世界", "v": "68657"},
                              {"n": "斗破苍穹手游", "v": "4337"}, {"n": "离火之境", "v": "9477"},
                              {"n": "一梦江湖", "v": "3082"}, {"n": "王牌竞速", "v": "6463"},
                              {"n": "高能英雄", "v": "8359"}, {"n": "斗罗大陆", "v": "6119"},
                              {"n": "未来之役", "v": "6831"}, {"n": "解限机", "v": "10961"},
                              {"n": "黎明觉醒：生机", "v": "6131"}, {"n": "诛仙2手游", "v": "10533"},
                              {"n": "游戏王：决斗链接", "v": "4451"}, {"n": "火柴人联盟3", "v": "10889"},
                              {"n": "曙光英雄", "v": "6169"}, {"n": "荣耀大天使", "v": "6477"},
                              {"n": "斗斗堂", "v": "7133"}, {"n": "石器时代：觉醒", "v": "9159"},
                              {"n": "偃武", "v": "67271"}, {"n": "七日世界", "v": "9995"},
                              {"n": "米加小镇", "v": "7269"}, {"n": "围棋", "v": "2694"},
                              {"n": "斗罗大陆2：绝世唐门", "v": "6581"}, {"n": "道友请留步", "v": "6629"},
                              {"n": "一拳超人：最强之男", "v": "4629"}, {"n": "斗罗大陆：武魂觉醒", "v": "6381"},
                              {"n": "原始征途", "v": "7713"}, {"n": "球球大作战", "v": "2411"},
                              {"n": "JJ麻将", "v": "9487"}]}
    }

    @staticmethod
    def _get_headers(need_referer: bool = False):
        headers = {"User-Agent": Huya.CHROME_UA}
        if need_referer:
            headers["Origin"] = "https://www.huya.com"
            headers["Referer"] = "https://www.huya.com/"
        return headers

    @staticmethod
    def _parse_stream_from_script(script: str):
        stream_pos = script.find("stream")
        if stream_pos == -1:
            return None

        colon_pos = script.find(":", stream_pos)
        if colon_pos == -1:
            return None

        value_start = colon_pos + 1
        while value_start < len(script) and script[value_start].isspace():
            value_start += 1

        if value_start >= len(script):
            return None

        first_char = script[value_start]

        if first_char == '"':
            end_quote = script.find('"', value_start + 1)
            if end_quote == -1:
                return None
            b64_str = script[value_start + 1:end_quote]
            return base64.b64decode(b64_str).decode('utf-8')
        elif first_char == '{':
            brace_count = 0
            i = value_start
            for i in range(value_start, len(script)):
                c = script[i]
                if c == '{':
                    brace_count += 1
                elif c == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        break
            else:
                return None
            return script[value_start:i + 1]
        return None

    @staticmethod
    def _parse_query_string(qs: str):
        result = {}
        if not qs:
            return result
        for pair in qs.split("&"):
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            result[urllib.parse.unquote(k)] = urllib.parse.unquote(v)
        return result

    @staticmethod
    def _build_stream_url(flv_url: str, stream_name: str, suffix: str) -> str:
        base = flv_url
        if not base.startswith("http://") and not base.startswith("https://"):
            base = "https://" + base
        elif base.startswith("http://"):
            base = "https://" + base[7:]
        return f"{base}/{stream_name}.{suffix}"

    @staticmethod
    def _md5_hex(text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    @staticmethod
    def _build_url(base_url: str, params: dict) -> str:
        if not params:
            return base_url
        encoded_params = urllib.parse.urlencode(params)
        if "?" in base_url:
            return base_url + "&" + encoded_params
        else:
            return base_url + "?" + encoded_params

    @staticmethod
    def _get_stream_params(fm: str, fs: str, ctype: str, ws_time: str,
                           stream_name: str, bit_rate: int):
        timestamp = int(time.time() * 1000)
        uid = 12340000 + random.randint(0, 9999)
        convert_uid = ((uid << 8) | (uid >> 24)) & 0xFFFFFFFF

        seqid = uid + timestamp

        try:
            decoded_fm = urllib.parse.unquote(fm)
            ws_secret_prefix = base64.b64decode(decoded_fm).decode('utf-8').split("_")[0]
        except Exception:
            ws_secret_prefix = ""

        hash_input1 = f"{seqid}|{ctype}|{Huya.CONSTANTS['t']}"
        ws_secret_hash = Huya._md5_hex(hash_input1)

        hash_input2 = f"{ws_secret_prefix}_{convert_uid}_{stream_name}_{ws_secret_hash}_{ws_time}"
        ws_secret = Huya._md5_hex(hash_input2)

        params = {
            "wsSecret": ws_secret,
            "wsTime": ws_time,
            "ctype": ctype,
            "fs": fs,
            "seqid": str(seqid),
            "u": str(convert_uid),
            "sdk_sid": str(timestamp),
            "ratio": str(bit_rate),
            **Huya.CONSTANTS
        }
        return params

    @classmethod
    def get_category_list(cls, gid: str, page: int = 1):
        url = cls.LIST_URL.format(gid=gid, page=page)
        resp = requests.get(url, headers=cls._get_headers(False))
        resp.raise_for_status()
        data = resp.json()
        vlist = data.get("vList", [])
        rooms = []
        for item in vlist:
            room_id = str(item.get("lProfileRoom"))
            nick = item.get("sNick", "未知主播")
            introduction = item.get("sIntroduction", "")
            game = item.get("sGameFullName", "未知游戏")
            screenshot = item.get("sScreenshot", "")
            if screenshot and not screenshot.startswith("http"):
                screenshot = "https:" + screenshot
            rooms.append({
                "room_id": room_id,
                "nick": nick,
                "game": game,
                "introduction": introduction,
                "screenshot": screenshot
            })
        has_more = len(vlist) == 120
        return rooms, has_more

    @classmethod
    def search_rooms(cls, keyword: str, page: int = 1):
        params = {
            "hiss": keyword,
            "afs": "",
            "p": page
        }
        resp = requests.get(cls.SEARCH_URL, params=params, headers=cls._get_headers(True))
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select(".live-list .video-info")
        rooms = []
        for item in items:
            title_el = item.select_one(".title a")
            if not title_el:
                continue
            room_url = title_el.get("href")
            if not room_url or "/" not in room_url:
                continue
            room_id = room_url.split("/")[-1].split("?")[0]
            nick = title_el.get("title", "未知主播")
            img_el = item.select_one("img")
            screenshot = img_el.get("src") or img_el.get("data-original", "")
            if screenshot and not screenshot.startswith("http"):
                screenshot = "https:" + screenshot
            game = item.select_one(".game-type") or ""
            game = game.get_text(strip=True) if game else "未知"
            rooms.append({
                "room_id": room_id,
                "nick": nick,
                "game": game,
                "introduction": "",
                "screenshot": screenshot
            })
        has_more = len(rooms) >= 20
        return rooms, has_more

    @classmethod
    def detail_content(cls, room_id: str):
        url = f"{cls.HUYA_URL}/{room_id}"
        resp = requests.get(url, headers=cls._get_headers(False))
        resp.raise_for_status()
        html = resp.text

        soup = BeautifulSoup(html, "html.parser")

        script_tag = None
        for script in soup.find_all("script"):
            if script.string and "var hyPlayerConfig = {" in script.string:
                script_tag = script
                break

        if not script_tag or not script_tag.string:
            raise ValueError("未能找到 hyPlayerConfig 脚本")

        stream_json_str = cls._parse_stream_from_script(script_tag.string)
        if not stream_json_str:
            raise ValueError("解析 stream 数据失败")

        stream_data = json.loads(stream_json_str)

        result = {}
        game_full_name = ""
        nick = ""
        introduction = ""

        data_list = stream_data.get("data")
        if not data_list:
            return result, game_full_name, nick, introduction

        data_item = data_list[0]
        live_info = data_item.get("gameLiveInfo", {})
        game_full_name = live_info.get("gameFullName", "")
        nick = live_info.get("nick", "")
        introduction = live_info.get("introduction", "")

        stream_info_list = data_item.get("gameStreamInfoList", [])
        if not stream_info_list:
            return result, game_full_name, nick, introduction

        multi_stream_info = stream_data.get("vMultiStreamInfo", [])

        for stream_info in stream_info_list:
            cdn_name = stream_info.get("sCdnType", "未知线路")
            urls = []

            flv_anti_code = urllib.parse.unquote(stream_info.get("sFlvAntiCode", ""))

            anti_params = cls._parse_query_string(flv_anti_code)
            filtered_params = {k: v for k, v in anti_params.items()
                               if k in cls.STREAM_URL_QUERYSTRING_PARAMS}

            fm = filtered_params.get("fm", "")
            fs = filtered_params.get("fs", "")
            ctype = filtered_params.get("ctype", "huya_live")
            ws_time = filtered_params.get("wsTime", "")

            base_flv_url = cls._build_stream_url(
                stream_info.get("sFlvUrl", ""),
                stream_info.get("sStreamName", ""),
                stream_info.get("sFlvUrlSuffix", "flv")
            )

            # base_hls_url = cls._build_stream_url(
            #     stream_info.get("sHlsUrl", ""),
            #     stream_info.get("sStreamName", ""),
            #     stream_info.get("sHlsUrlSuffix", "m3u8")
            # )

            for multi in multi_stream_info:
                display_name = multi.get("sDisplayName", "未知画质")
                bit_rate = multi.get("iBitRate")
                params = cls._get_stream_params(
                    fm=fm,
                    fs=fs,
                    ctype=ctype,
                    ws_time=ws_time,
                    stream_name=stream_info.get("sStreamName", ""),
                    bit_rate=bit_rate
                )

                final_flv_url = cls._build_url(base_flv_url, params)
                # final_hls_url = cls._build_url(base_hls_url, params)
                urls.append(f"{"FLV " + display_name}${final_flv_url}")
                # urls.append(f"{"HLS" + display_name}${final_hls_url}")

            if urls:
                result[cdn_name] = "#".join(urls)

        return result, game_full_name, nick, introduction


class ImageLoadWorker(QObject):
    finished = Signal(str, QPixmap)

    def __init__(self, url):
        super().__init__()
        self.url = url

    @Slot()
    def run(self):
        try:
            data = requests.get(self.url, timeout=10).content
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            pixmap = pixmap.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                   Qt.TransformationMode.SmoothTransformation)
            self.finished.emit(self.url, pixmap)
        except:
            self.finished.emit(self.url, QPixmap())


class RoomItem(QWidget):
    def __init__(self, room_data, main_window, parent=None):  # 新增 main_window 参数
        super().__init__(parent)
        self.room_id = room_data["room_id"]
        self.room_data = room_data
        self.main_window = main_window  # 保存引用

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.img_label = QLabel()
        self.img_label.setFixedSize(160, 90)
        self.img_label.setStyleSheet("background: black;")
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setText("加载中...")
        layout.addWidget(self.img_label)

        info_layout = QVBoxLayout()
        nick_label = QLabel(f"<b>{room_data['nick']}</b>")
        nick_label.setStyleSheet("font-size: 15px;")
        game_label = QLabel(room_data['game'])
        game_label.setStyleSheet("color: #666; font-size: 13px;")
        intro_text = room_data['introduction'][:30] + "..." if len(room_data['introduction']) > 30 else room_data[
            'introduction']
        intro_label = QLabel(intro_text)
        intro_label.setStyleSheet("color: #888; font-size: 12px;")
        info_layout.addWidget(nick_label)
        info_layout.addWidget(game_label)
        if room_data['introduction']:
            info_layout.addWidget(intro_label)
        info_layout.addStretch()
        layout.addLayout(info_layout, stretch=1)

        self.setLayout(layout)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("RoomItem:hover {background: #f0f0f0;}")

        if room_data["screenshot"]:
            worker = ImageLoadWorker(room_data["screenshot"])
            worker.finished.connect(self.on_image_loaded)
            runnable = QRunnable.create(worker.run)
            QThreadPool.globalInstance().start(runnable)

    def on_image_loaded(self, url, pixmap):
        if url == self.room_data["screenshot"]:
            if not pixmap.isNull():
                self.img_label.setPixmap(pixmap)
            else:
                self.img_label.setText("加载失败")
                self.img_label.setStyleSheet("color: white; background: #333;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.main_window.on_room_clicked(self.room_id)  # 直接调用


class FetchListThread(QThread):
    finished = Signal(list, bool)

    def __init__(self, gid, page=1):
        super().__init__()
        self.gid = gid
        self.page = page

    def run(self):
        try:
            rooms, has_more = Huya.get_category_list(self.gid, self.page)
            self.finished.emit(rooms, has_more)
        except Exception:
            self.finished.emit([], False)


class SearchThread(QThread):
    finished = Signal(list, bool)

    def __init__(self, keyword, page=1):
        super().__init__()
        self.keyword = keyword
        self.page = page

    def run(self):
        try:
            rooms, has_more = Huya.search_rooms(self.keyword, self.page)
            self.finished.emit(rooms, has_more)
        except Exception:
            self.finished.emit([], False)


class FetchDetailThread(QThread):
    finished = Signal(dict, str, str, str)

    def __init__(self, room_id):
        super().__init__()
        self.room_id = room_id

    def run(self):
        try:
            streams, game, nick, intro = Huya.detail_content(self.room_id)
            self.finished.emit(streams, game, nick, intro)
        except Exception:
            self.finished.emit({}, "", "", "")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("虎牙直播解析工具")
        self.resize(1450, 840)

        self.favorites_file = os.path.join(os.path.dirname(__file__), "favorites.json")
        self.favorites = {'100270': "瓦莉拉", "528300": "安德罗妮"}
        self.current_gid = '393'
        self.current_page = 1
        self.has_more = False
        self.is_search_mode = False
        self.current_keyword = ""

        self.current_room_id = None

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)

        cat_group = QGroupBox("分类")
        cat_layout = QVBoxLayout(cat_group)
        self.cat_tree = QTreeWidget()
        self.cat_tree.setHeaderHidden(True)
        self.cat_tree.itemClicked.connect(self.on_cat_clicked)
        cat_layout.addWidget(self.cat_tree)
        left_layout.addWidget(cat_group)

        self.populate_category_tree()

        fav_group = QGroupBox("收藏房间（双击打开，右键删除）")
        fav_layout = QVBoxLayout(fav_group)
        self.fav_list = QListWidget()
        self.fav_list.itemDoubleClicked.connect(self.on_fav_double_clicked)
        self.fav_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fav_list.customContextMenuRequested.connect(self.show_fav_context_menu)
        fav_layout.addWidget(self.fav_list)
        left_layout.addWidget(fav_group)

        splitter.addWidget(left_widget)

        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        right_layout.setSpacing(6)

        # 搜索栏：固定高度，不拉伸
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入主播名/房间号/关键词搜索")
        self.search_input.returnPressed.connect(self.do_search)
        search_layout.addWidget(self.search_input, stretch=1)

        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self.do_search)
        search_layout.addWidget(self.search_btn)

        # 把搜索栏放进一个容器并限制高度
        search_container = QWidget(self)
        search_container.setLayout(search_layout)
        search_container.setFixedHeight(50)  # 固定搜索栏高度
        right_layout.addWidget(search_container)

        # 直播间列表：让它占更多空间
        list_group = QGroupBox("直播间列表")
        list_layout = QVBoxLayout(list_group)

        self.room_list = QListWidget()
        self.room_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.room_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.room_list.setFlow(QListWidget.Flow.LeftToRight)

        self.room_list.setSpacing(10)
        self.room_list.setWrapping(True)
        self.room_list.setIconSize(QSize(160, 90))
        list_layout.addWidget(self.room_list)

        self.load_more_btn = QPushButton("加载更多")
        self.load_more_btn.clicked.connect(self.load_more_rooms)
        self.load_more_btn.setEnabled(False)
        list_layout.addWidget(self.load_more_btn)

        right_layout.addWidget(list_group, stretch=3)

        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        right_layout.addWidget(detail_scroll, stretch=2)

        self.content_widget = QWidget(self)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.addStretch()  # 确保内容从顶部开始
        detail_scroll.setWidget(self.content_widget)

        splitter.addWidget(right_widget)
        splitter.setSizes([260, 1340])

        self.load_favorites()
        self.fetch_category_list()

    def populate_category_tree(self):
        self.cat_tree.clear()
        for main_name in Huya.MAIN_CATEGORIES:
            main_item = QTreeWidgetItem(self.cat_tree, [main_name])
            main_item.setForeground(0, QBrush(QColor("#0066cc")))
            main_item.setFlags(main_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)

            sub_data = Huya.SUB_CATEGORIES_DATA.get(main_name, {})
            for group in sub_data.values():
                for sub in group:
                    sub_item = QTreeWidgetItem(main_item, [sub["n"]])
                    sub_item.setData(0, Qt.ItemDataRole.UserRole, sub["v"])

            main_item.setExpanded(False)

    def on_cat_clicked(self, item: QTreeWidgetItem):
        gid = item.data(0, Qt.ItemDataRole.UserRole)
        if gid is None:
            return
        self.current_gid = gid
        self.is_search_mode = False
        self.current_page = 1
        self.room_list.clear()
        self.load_more_btn.setEnabled(False)
        self.clear_content()
        self.fetch_category_list()

    def load_favorites(self):
        if os.path.exists(self.favorites_file):
            try:
                with open(self.favorites_file, "r", encoding="utf-8") as f:
                    self.favorites = json.load(f)
            except:
                self.favorites = {}
        self.update_fav_list()

    def save_favorites(self):
        try:
            with open(self.favorites_file, "w", encoding="utf-8") as f:
                json.dump(self.favorites, f, ensure_ascii=False, indent=2)
        except:
            pass

    def update_fav_list(self):
        self.fav_list.clear()
        for room_id, name in sorted(self.favorites.items(), key=lambda x: x[1]):
            item = QListWidgetItem(f"{name} ({room_id})")
            item.setData(Qt.ItemDataRole.UserRole, room_id)
            self.fav_list.addItem(item)

    def add_favorite(self, room_id: str, room_name: str):
        if room_id in self.favorites:
            return
        self.favorites[room_id] = room_name
        self.save_favorites()
        self.update_fav_list()

    def on_fav_double_clicked(self, item: QListWidgetItem):
        room_id = item.data(Qt.ItemDataRole.UserRole)
        self.fetch_streams(room_id)

    def show_fav_context_menu(self, pos):
        item = self.fav_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        delete_action = menu.addAction("删除此收藏")
        action = menu.exec(self.fav_list.mapToGlobal(pos))
        if action == delete_action:
            room_id = item.data(Qt.ItemDataRole.UserRole)
            del self.favorites[room_id]
            self.save_favorites()
            self.update_fav_list()

    def do_search(self):
        keyword = self.search_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "提示", "请输入搜索关键词")
            return
        self.current_keyword = keyword
        self.is_search_mode = True
        self.current_page = 1
        self.room_list.clear()
        self.load_more_btn.setEnabled(False)
        self.clear_content()
        self.search_rooms()

    def search_rooms(self):
        loading_item = QListWidgetItem("搜索中...")
        self.room_list.addItem(loading_item)
        self.search_thread = SearchThread(self.current_keyword, self.current_page)
        self.search_thread.finished.connect(self.on_list_loaded)
        self.search_thread.start()

    def fetch_category_list(self):
        loading_item = QListWidgetItem("加载中...")
        self.room_list.addItem(loading_item)
        self.fetch_thread = FetchListThread(self.current_gid, self.current_page)
        self.fetch_thread.finished.connect(self.on_list_loaded)
        self.fetch_thread.start()

    def on_list_loaded(self, rooms, has_more):
        self.room_list.clear()
        for room in rooms:
            widget = RoomItem(room, self)
            item = QListWidgetItem()
            item.setSizeHint(QSize(360, 110))
            self.room_list.addItem(item)
            self.room_list.setItemWidget(item, widget)
        self.has_more = has_more
        self.load_more_btn.setEnabled(has_more)

    def load_more_rooms(self):
        if not self.has_more:
            return
        self.current_page += 1
        if self.is_search_mode:
            self.search_rooms()
        else:
            self.fetch_category_list()

    def on_room_clicked(self, room_id):
        if not self.current_room_id:
            self.current_room_id = room_id
            self.fetch_streams(room_id)

    def fetch_streams(self, room_id: str):
        self.clear_content()

        loading_label = QLabel("<i style='font-size:14px; color:#888;'>正在加载直播流地址...</i>")
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_label.setStyleSheet("padding: 30px;")
        self.content_layout.addWidget(loading_label)

        if hasattr(self, "detail_thread"):
            try:
                self.detail_thread.finished.disconnect()
            except TypeError:
                pass

        self.detail_thread = FetchDetailThread(room_id)
        self.detail_thread.finished.connect(
            lambda streams, game, nick, intro: self.on_detail_loaded(streams, game, nick, intro, room_id)
        )

        self.detail_thread.finished.connect(loading_label.deleteLater)

        self.detail_thread.start()

    def copy_to_clipboard(self, url: str):
        """复制直播地址到剪贴板"""
        QApplication.clipboard().setText(url)
        QMessageBox.information(self, "提示", "直播地址已复制到剪贴板！")

    def play_in_chrome(self, url: str):

        # 假设 play_flv.html 放在程序目录下
        html_path = os.path.join(os.path.dirname(__file__), "player.html")

        if not os.path.exists(html_path):
            QMessageBox.warning(self, "错误", "找不到 player.html，请先创建该文件")
            return

        # 对 url 做编码，防止特殊字符问题
        encoded_url = urllib.parse.quote(url, safe='')
        full_url = f"file:///{html_path}?url={encoded_url}"

        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",  # 有时会多一个
        ]

        launched = False
        for path in chrome_paths:
            if os.path.exists(path):
                try:
                    # --new-window 防止复用已有窗口导致参数丢失
                    # --app 模式更干净（无地址栏、标签页）
                    subprocess.Popen([path, "--app=" + full_url, "--new-window"])
                    launched = True
                    break
                except:
                    continue

        if not launched:
            import webbrowser
            webbrowser.open(full_url)
            QMessageBox.information(self, "提示", "已用系统默认浏览器打开（未找到独立 Chrome）")

    def on_detail_loaded(self, streams, game_full_name, nick, introduction, room_id):
        if not streams:
            QMessageBox.information(self, "提示", "未开播或房间不存在")
            self.current_room_id = None
            return

        self.clear_content()

        display_title = f"{game_full_name} - {nick} - {introduction}" if game_full_name and nick else nick or room_id

        title_layout = QHBoxLayout()
        title_label = QLabel(f"<b style='font-size:18px'>{display_title} (房间号: {room_id})</b>")
        title_layout.addWidget(title_label)

        if room_id not in self.favorites:
            add_btn = QPushButton("添加到收藏")
            add_btn.clicked.connect(lambda: self.add_favorite(room_id, display_title))
            title_layout.addWidget(add_btn)

        title_layout.addStretch()
        self.content_layout.addLayout(title_layout)

        for cdn, url_list in streams.items():
            group = QGroupBox(f"线路: {cdn}")
            grid = QGridLayout()
            group.setLayout(grid)

            row = col = 0
            for item in url_list.split("#"):
                if not item:
                    continue
                name, url = item.split("$", 1)

                container = QWidget()
                hbox = QHBoxLayout(container)
                hbox.setContentsMargins(4, 4, 4, 4)
                hbox.setSpacing(5)

                # 1. PotPlayer 播放（主按钮，保持原来体验）
                play_btn = QPushButton(name)
                play_btn.setToolTip(url)
                play_btn.setFixedWidth(100)
                pot_title = f"{game_full_name} - {nick} - {introduction}".strip()
                play_url = f'"{url}" /title="{pot_title}" /referer=["]https://www.huya.com["] /headers=["]Origin=https://www.huya.com["]'
                play_btn.clicked.connect(lambda _, u=play_url: self.play_in_potplayer(u))
                hbox.addWidget(play_btn)

                # 2. Chrome 播放按钮
                chrome_btn = QPushButton("Chrome播放")
                chrome_btn.setFixedWidth(100)
                chrome_btn.clicked.connect(lambda _, u=url: self.play_in_chrome(u))
                hbox.addWidget(chrome_btn)

                grid.addWidget(container, row, col)
                col += 1
                if col > 4:
                    col = 0
                    row += 1

            self.content_layout.addWidget(group)

        self.content_layout.addStretch()
        self.current_room_id = None

    def clear_content(self):
        """彻底清除 content_layout 中的所有内容，包括子布局和 stretch"""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget:
                widget.deleteLater()
            else:
                layout = item.layout()
                if layout:
                    self.clear_layout(layout)  # 递归删除子布局（关键）

    def clear_layout(self, layout):
        """递归清除布局内所有内容"""
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget:
                widget.deleteLater()
            else:
                sub_layout = item.layout()
                if sub_layout:
                    self.clear_layout(sub_layout)

    def play_in_potplayer(self, url_with_title: str):
        potplayer_exe = r"C:\SoftWare\PotPlayer\PotPlayerMini64.exe"
        if not os.path.isfile(potplayer_exe):
            QMessageBox.warning(self, "未找到PotPlayer", "请修改代码中的PotPlayer路径，或手动复制链接播放")
            return
        try:
            url_with_title = f'{potplayer_exe} {url_with_title}'
            subprocess.Popen(url_with_title, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动失败: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
