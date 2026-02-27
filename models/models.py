"""
灾害预警数据模型
适配数据源架构
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# 中国所有省级行政区的名称列表
CHINA_PROVINCES = [
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "台湾",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
]


# 中国所有地级市列表（不含港澳台）
CHINA_CITIES = [
    "石家庄市", "唐山市", "秦皇岛市", "邯郸市", "邢台市", "保定市", "张家口市", "承德市", "沧州市", "廊坊市", "衡水市",
    "太原市", "大同市", "阳泉市", "长治市", "晋城市", "朔州市", "晋中市", "运城市", "忻州市", "临汾市", "吕梁市",
    "呼和浩特市", "包头市", "乌海市", "赤峰市", "通辽市", "鄂尔多斯市", "呼伦贝尔市", "巴彦淖尔市", "乌兰察布市", "兴安盟", "锡林郭勒盟", "阿拉善盟",
    "沈阳市", "大连市", "鞍山市", "抚顺市", "本溪市", "丹东市", "锦州市", "营口市", "阜新市", "辽阳市", "盘锦市", "铁岭市", "朝阳市", "葫芦岛市",
    "长春市", "吉林市", "四平市", "辽源市", "通化市", "白山市", "松原市", "白城市", "延边朝鲜族自治州",
    "哈尔滨市", "齐齐哈尔市", "鸡西市", "鹤岗市", "双鸭山市", "大庆市", "伊春市", "佳木斯市", "七台河市", "牡丹江市", "黑河市", "绥化市", "大兴安岭地区",
    "南京市", "无锡市", "徐州市", "常州市", "苏州市", "南通市", "连云港市", "淮安市", "盐城市", "扬州市", "镇江市", "泰州市", "宿迁市",
    "杭州市", "宁波市", "温州市", "嘉兴市", "湖州市", "绍兴市", "金华市", "衢州市", "舟山市", "台州市", "丽水市",
    "合肥市", "芜湖市", "蚌埠市", "淮南市", "马鞍山市", "淮北市", "铜陵市", "安庆市", "黄山市", "滁州市", "阜阳市", "宿州市", "六安市", "亳州市", "池州市", "宣城市",
    "福州市", "厦门市", "莆田市", "三明市", "泉州市", "漳州市", "南平市", "龙岩市", "宁德市",
    "南昌市", "景德镇市", "萍乡市", "九江市", "新余市", "鹰潭市", "赣州市", "吉安市", "宜春市", "抚州市", "上饶市",
    "济南市", "青岛市", "淄博市", "枣庄市", "东营市", "烟台市", "潍坊市", "济宁市", "泰安市", "威海市", "日照市", "临沂市", "德州市", "聊城市", "滨州市", "菏泽市",
    "郑州市", "开封市", "洛阳市", "平顶山市", "安阳市", "鹤壁市", "新乡市", "焦作市", "濮阳市", "许昌市", "漯河市", "三门峡市", "南阳市", "商丘市", "信阳市", "周口市", "驻马店市", "济源市",
    "武汉市", "黄石市", "十堰市", "宜昌市", "襄阳市", "鄂州市", "荆门市", "孝感市", "荆州市", "黄冈市", "咸宁市", "随州市", "恩施土家族苗族自治州", "仙桃市", "潜江市", "天门市", "神农架林区",
    "长沙市", "株洲市", "湘潭市", "衡阳市", "邵阳市", "岳阳市", "常德市", "张家界市", "益阳市", "郴州市", "永州市", "怀化市", "娄底市", "湘西土家族苗族自治州",
    "广州市", "韶关市", "深圳市", "珠海市", "汕头市", "佛山市", "江门市", "湛江市", "茂名市", "肇庆市", "惠州市", "梅州市", "汕尾市", "河源市", "阳江市", "清远市", "东莞市", "中山市", "潮州市", "揭阳市", "云浮市",
    "南宁市", "柳州市", "桂林市", "梧州市", "北海市", "防城港市", "钦州市", "贵港市", "玉林市", "百色市", "贺州市", "河池市", "来宾市", "崇左市",
    "海口市", "三亚市", "三沙市", "儋州市", "五指山市", "文昌市", "琼海市", "万宁市", "东方市",
    "成都市", "自贡市", "攀枝花市", "泸州市", "德阳市", "绵阳市", "广元市", "遂宁市", "内江市", "乐山市", "南充市", "眉山市", "宜宾市", "广安市", "达州市", "雅安市", "巴中市", "资阳市", "阿坝藏族羌族自治州", "甘孜藏族自治州", "凉山彝族自治州",
    "贵阳市", "六盘水市", "遵义市", "安顺市", "毕节市", "铜仁市", "黔西南布依族苗族自治州", "黔东南苗族侗族自治州", "黔南布依族苗族自治州",
    "昆明市", "曲靖市", "玉溪市", "保山市", "昭通市", "丽江市", "普洱市", "临沧市", "楚雄彝族自治州", "红河哈尼族彝族自治州", "文山壮族苗族自治州", "西双版纳傣族自治州", "大理白族自治州", "德宏傣族景颇族自治州", "怒江傈僳族自治州", "迪庆藏族自治州",
    "西安市", "铜川市", "宝鸡市", "咸阳市", "渭南市", "延安市", "汉中市", "榆林市", "安康市", "商洛市",
    "兰州市", "嘉峪关市", "金昌市", "白银市", "天水市", "武威市", "张掖市", "平凉市", "酒泉市", "庆阳市", "定西市", "陇南市", "临夏回族自治州", "甘南藏族自治州",
    "西宁市", "海东市", "海北藏族自治州", "黄南藏族自治州", "海南藏族自治州", "果洛藏族自治州", "玉树藏族自治州", "海西蒙古族藏族自治州",
    "银川市", "石嘴山市", "吴忠市", "固原市", "中卫市",
    "乌鲁木齐市", "克拉玛依市", "吐鲁番市", "哈密市", "昌吉回族自治州", "博尔塔拉蒙古自治州", "巴音郭楞蒙古自治州", "阿克苏地区", "克孜勒苏柯尔克孜自治州", "喀什地区", "和田地区", "伊犁哈萨克自治州", "塔城地区", "阿勒泰地区",
    "台北市", "新北市", "桃园市", "台中市", "台南市", "高雄市", "基隆市", "新竹市", "嘉义市", "宜兰县", "新竹县", "苗栗县", "彰化县", "南投县", "云林县", "嘉义县", "屏东县", "花莲县", "台东县", "澎湖县",
    # 香港
    "中西区", "湾仔区", "东区", "南区", "油尖旺区", "深水埗区", "九龙城区", "黄大仙区", "观塘区", "荃湾区", "屯门区", "元朗区", "北区", "大埔区", "沙田区", "西贡区", "离岛区", "葵青区",
    # 澳门
    "花地玛堂区", "花王堂区", "望德堂区", "大堂区", "风顺堂区", "嘉模堂区", "路氹城", "圣方济各堂区",
]

# 地级市到省份的映射
CITY_TO_PROVINCE = {
    # 河北省
    "石家庄市": "河北", "唐山市": "河北", "秦皇岛市": "河北", "邯郸市": "河北", "邢台市": "河北",
    "保定市": "河北", "张家口市": "河北", "承德市": "河北", "沧州市": "河北", "廊坊市": "河北", "衡水市": "河北",
    # 山西省
    "太原市": "山西", "大同市": "山西", "阳泉市": "山西", "长治市": "山西", "晋城市": "山西",
    "朔州市": "山西", "晋中市": "山西", "运城市": "山西", "忻州市": "山西", "临汾市": "山西", "吕梁市": "山西",
    # 内蒙古
    "呼和浩特市": "内蒙古", "包头市": "内蒙古", "乌海市": "内蒙古", "赤峰市": "内蒙古", "通辽市": "内蒙古",
    "鄂尔多斯市": "内蒙古", "呼伦贝尔市": "内蒙古", "巴彦淖尔市": "内蒙古", "乌兰察布市": "内蒙古",
    "兴安盟": "内蒙古", "锡林郭勒盟": "内蒙古", "阿拉善盟": "内蒙古",
    # 辽宁省
    "沈阳市": "辽宁", "大连市": "辽宁", "鞍山市": "辽宁", "抚顺市": "辽宁", "本溪市": "辽宁",
    "丹东市": "辽宁", "锦州市": "辽宁", "营口市": "辽宁", "阜新市": "辽宁", "辽阳市": "辽宁",
    "盘锦市": "辽宁", "铁岭市": "辽宁", "朝阳市": "辽宁", "葫芦岛市": "辽宁",
    # 吉林省
    "长春市": "吉林", "吉林市": "吉林", "四平市": "吉林", "辽源市": "吉林", "通化市": "吉林",
    "白山市": "吉林", "松原市": "吉林", "白城市": "吉林", "延边朝鲜族自治州": "吉林",
    # 黑龙江省
    "哈尔滨市": "黑龙江", "齐齐哈尔市": "黑龙江", "鸡西市": "黑龙江", "鹤岗市": "黑龙江", "双鸭山市": "黑龙江",
    "大庆市": "黑龙江", "伊春市": "黑龙江", "佳木斯市": "黑龙江", "七台河市": "黑龙江", "牡丹江市": "黑龙江",
    "黑河市": "黑龙江", "绥化市": "黑龙江", "大兴安岭地区": "黑龙江",
    # 江苏省
    "南京市": "江苏", "无锡市": "江苏", "徐州市": "江苏", "常州市": "江苏", "苏州市": "江苏",
    "南通市": "江苏", "连云港市": "江苏", "淮安市": "江苏", "盐城市": "江苏", "扬州市": "江苏",
    "镇江市": "江苏", "泰州市": "江苏", "宿迁市": "江苏",
    # 浙江省
    "杭州市": "浙江", "宁波市": "浙江", "温州市": "浙江", "嘉兴市": "浙江", "湖州市": "浙江",
    "绍兴市": "浙江", "金华市": "浙江", "衢州市": "浙江", "舟山市": "浙江", "台州市": "浙江", "丽水市": "浙江",
    # 安徽省
    "合肥市": "安徽", "芜湖市": "安徽", "蚌埠市": "安徽", "淮南市": "安徽", "马鞍山市": "安徽",
    "淮北市": "安徽", "铜陵市": "安徽", "安庆市": "安徽", "黄山市": "安徽", "滁州市": "安徽",
    "阜阳市": "安徽", "宿州市": "安徽", "六安市": "安徽", "亳州市": "安徽", "池州市": "安徽", "宣城市": "安徽",
    # 福建省
    "福州市": "福建", "厦门市": "福建", "莆田市": "福建", "三明市": "福建", "泉州市": "福建",
    "漳州市": "福建", "南平市": "福建", "龙岩市": "福建", "宁德市": "福建",
    # 江西省
    "南昌市": "江西", "景德镇市": "江西", "萍乡市": "江西", "九江市": "江西", "新余市": "江西",
    "鹰潭市": "江西", "赣州市": "江西", "吉安市": "江西", "宜春市": "江西", "抚州市": "江西", "上饶市": "江西",
    # 山东省
    "济南市": "山东", "青岛市": "山东", "淄博市": "山东", "枣庄市": "山东", "东营市": "山东",
    "烟台市": "山东", "潍坊市": "山东", "济宁市": "山东", "泰安市": "山东", "威海市": "山东",
    "日照市": "山东", "临沂市": "山东", "德州市": "山东", "聊城市": "山东", "滨州市": "山东", "菏泽市": "山东",
    # 河南省
    "郑州市": "河南", "开封市": "河南", "洛阳市": "河南", "平顶山市": "河南", "安阳市": "河南",
    "鹤壁市": "河南", "新乡市": "河南", "焦作市": "河南", "濮阳市": "河南", "许昌市": "河南",
    "漯河市": "河南", "三门峡市": "河南", "南阳市": "河南", "商丘市": "河南", "信阳市": "河南",
    "周口市": "河南", "驻马店市": "河南", "济源市": "河南",
    # 湖北省
    "武汉市": "湖北", "黄石市": "湖北", "十堰市": "湖北", "宜昌市": "湖北", "襄阳市": "湖北",
    "鄂州市": "湖北", "荆门市": "湖北", "孝感市": "湖北", "荆州市": "湖北", "黄冈市": "湖北",
    "咸宁市": "湖北", "随州市": "湖北", "恩施土家族苗族自治州": "湖北",
    "仙桃市": "湖北", "潜江市": "湖北", "天门市": "湖北", "神农架林区": "湖北",
    # 湖南省
    "长沙市": "湖南", "株洲市": "湖南", "湘潭市": "湖南", "衡阳市": "湖南", "邵阳市": "湖南",
    "岳阳市": "湖南", "常德市": "湖南", "张家界市": "湖南", "益阳市": "湖南", "郴州市": "湖南",
    "永州市": "湖南", "怀化市": "湖南", "娄底市": "湖南", "湘西土家族苗族自治州": "湖南",
    # 广东省
    "广州市": "广东", "韶关市": "广东", "深圳市": "广东", "珠海市": "广东", "汕头市": "广东",
    "佛山市": "广东", "江门市": "广东", "湛江市": "广东", "茂名市": "广东", "肇庆市": "广东",
    "惠州市": "广东", "梅州市": "广东", "汕尾市": "广东", "河源市": "广东", "阳江市": "广东",
    "清远市": "广东", "东莞市": "广东", "中山市": "广东", "潮州市": "广东", "揭阳市": "广东", "云浮市": "广东",
    # 广西
    "南宁市": "广西", "柳州市": "广西", "桂林市": "广西", "梧州市": "广西", "北海市": "广西",
    "防城港市": "广西", "钦州市": "广西", "贵港市": "广西", "玉林市": "广西", "百色市": "广西",
    "贺州市": "广西", "河池市": "广西", "来宾市": "广西", "崇左市": "广西",
    # 海南省
    "海口市": "海南", "三亚市": "海南", "三沙市": "海南", "儋州市": "海南", "五指山市": "海南",
    "文昌市": "海南", "琼海市": "海南", "万宁市": "海南", "东方市": "海南",
    # 四川省
    "成都市": "四川", "自贡市": "四川", "攀枝花市": "四川", "泸州市": "四川", "德阳市": "四川",
    "绵阳市": "四川", "广元市": "四川", "遂宁市": "四川", "内江市": "四川", "乐山市": "四川",
    "南充市": "四川", "眉山市": "四川", "宜宾市": "四川", "广安市": "四川", "达州市": "四川",
    "雅安市": "四川", "巴中市": "四川", "资阳市": "四川",
    "阿坝藏族羌族自治州": "四川", "甘孜藏族自治州": "四川", "凉山彝族自治州": "四川",
    # 贵州省
    "贵阳市": "贵州", "六盘水市": "贵州", "遵义市": "贵州", "安顺市": "贵州", "毕节市": "贵州",
    "铜仁市": "贵州", "黔西南布依族苗族自治州": "贵州", "黔东南苗族侗族自治州": "贵州", "黔南布依族苗族自治州": "贵州",
    # 云南省
    "昆明市": "云南", "曲靖市": "云南", "玉溪市": "云南", "保山市": "云南", "昭通市": "云南",
    "丽江市": "云南", "普洱市": "云南", "临沧市": "云南",
    "楚雄彝族自治州": "云南", "红河哈尼族彝族自治州": "云南", "文山壮族苗族自治州": "云南",
    "西双版纳傣族自治州": "云南", "大理白族自治州": "云南", "德宏傣族景颇族自治州": "云南",
    "怒江傈僳族自治州": "云南", "迪庆藏族自治州": "云南",
    # 陕西省
    "西安市": "陕西", "铜川市": "陕西", "宝鸡市": "陕西", "咸阳市": "陕西", "渭南市": "陕西",
    "延安市": "陕西", "汉中市": "陕西", "榆林市": "陕西", "安康市": "陕西", "商洛市": "陕西",
    # 甘肃省
    "兰州市": "甘肃", "嘉峪关市": "甘肃", "金昌市": "甘肃", "白银市": "甘肃", "天水市": "甘肃",
    "武威市": "甘肃", "张掖市": "甘肃", "平凉市": "甘肃", "酒泉市": "甘肃", "庆阳市": "甘肃",
    "定西市": "甘肃", "陇南市": "甘肃", "临夏回族自治州": "甘肃", "甘南藏族自治州": "甘肃",
    # 青海省
    "西宁市": "青海", "海东市": "青海",
    "海北藏族自治州": "青海", "黄南藏族自治州": "青海", "海南藏族自治州": "青海",
    "果洛藏族自治州": "青海", "玉树藏族自治州": "青海", "海西蒙古族藏族自治州": "青海",
    # 宁夏
    "银川市": "宁夏", "石嘴山市": "宁夏", "吴忠市": "宁夏", "固原市": "宁夏", "中卫市": "宁夏",
    # 新疆
    "乌鲁木齐市": "新疆", "克拉玛依市": "新疆", "吐鲁番市": "新疆", "哈密市": "新疆",
    "昌吉回族自治州": "新疆", "博尔塔拉蒙古自治州": "新疆", "巴音郭楞蒙古自治州": "新疆",
    "阿克苏地区": "新疆", "克孜勒苏柯尔克孜自治州": "新疆", "喀什地区": "新疆", "和田地区": "新疆",
    "伊犁哈萨克自治州": "新疆", "塔城地区": "新疆", "阿勒泰地区": "新疆",
    # 台湾
    "台北市": "台湾", "新北市": "台湾", "桃园市": "台湾", "台中市": "台湾",
    "台南市": "台湾", "高雄市": "台湾", "基隆市": "台湾", "新竹市": "台湾", "嘉义市": "台湾",
    "宜兰县": "台湾", "新竹县": "台湾", "苗栗县": "台湾", "彰化县": "台湾", "南投县": "台湾",
    "云林县": "台湾", "嘉义县": "台湾", "屏东县": "台湾", "花莲县": "台湾", "台东县": "台湾", "澎湖县": "台湾",
    # 香港
    "中西区": "香港", "湾仔区": "香港", "东区": "香港", "南区": "香港",
    "油尖旺区": "香港", "深水埗区": "香港", "九龙城区": "香港", "黄大仙区": "香港", "观塘区": "香港",
    "荃湾区": "香港", "屯门区": "香港", "元朗区": "香港", "北区": "香港", "大埔区": "香港",
    "沙田区": "香港", "西贡区": "香港", "离岛区": "香港", "葵青区": "香港",
    # 澳门
    "花地玛堂区": "澳门", "花王堂区": "澳门", "望德堂区": "澳门", "大堂区": "澳门",
    "风顺堂区": "澳门", "嘉模堂区": "澳门", "路氹城": "澳门", "圣方济各堂区": "澳门",
}


class DisasterType(Enum):
    """灾害类型"""

    EARTHQUAKE = "earthquake"
    EARTHQUAKE_WARNING = "earthquake_warning"
    TSUNAMI = "tsunami"
    WEATHER_ALARM = "weather_alarm"


class DataSource(Enum):
    """数据源类型 - 适配架构"""

    # FAN Studio 数据源
    FAN_STUDIO_CENC = "fan_studio_cenc"  # 中国地震台网
    FAN_STUDIO_CEA = "fan_studio_cea"  # 中国地震预警网
    FAN_STUDIO_CEA_PR = "fan_studio_cea_pr"  # 中国地震预警网(省级)
    FAN_STUDIO_CWA = "fan_studio_cwa"  # 台湾中央气象署(预警)
    FAN_STUDIO_CWA_REPORT = "fan_studio_cwa_report"  # 台湾中央气象署(报告)
    FAN_STUDIO_USGS = "fan_studio_usgs"  # USGS
    FAN_STUDIO_JMA = "fan_studio_jma"  # 日本气象厅地震预警
    FAN_STUDIO_WEATHER = "fan_studio_weather"  # 中国气象局气象预警
    FAN_STUDIO_TSUNAMI = "fan_studio_tsunami"  # 海啸预警

    # P2P 数据源
    P2P_EEW = "p2p_eew"  # P2P地震情報緊急地震速報
    P2P_EARTHQUAKE = "p2p_earthquake"  # P2P地震情報
    P2P_TSUNAMI = "p2p_tsunami"  # P2P海啸预报

    # Wolfx 数据源
    WOLFX_JMA_EEW = "wolfx_jma_eew"  # Wolfx日本气象厅紧急地震速报
    WOLFX_CENC_EEW = "wolfx_cenc_eew"  # Wolfx中国地震台网预警
    WOLFX_CWA_EEW = "wolfx_cwa_eew"  # Wolfx台湾地震预警
    WOLFX_CENC_EQ = "wolfx_cenc_eq"  # Wolfx中国地震台网地震测定
    WOLFX_JMA_EQ = "wolfx_jma_eq"  # Wolfx日本气象厅地震情报

    # Global Quake 数据源
    GLOBAL_QUAKE = "global_quake"  # Global Quake服务器


# 数据源ID映射
DATA_SOURCE_MAPPING = {
    # EEW预警数据源
    "cea_fanstudio": DataSource.FAN_STUDIO_CEA,
    "cea_pr_fanstudio": DataSource.FAN_STUDIO_CEA_PR,
    "cea_wolfx": DataSource.WOLFX_CENC_EEW,
    "cwa_fanstudio": DataSource.FAN_STUDIO_CWA,
    "cwa_fanstudio_report": DataSource.FAN_STUDIO_CWA_REPORT,
    "cwa_wolfx": DataSource.WOLFX_CWA_EEW,
    "jma_fanstudio": DataSource.FAN_STUDIO_JMA,
    "jma_p2p": DataSource.P2P_EEW,
    "jma_wolfx": DataSource.WOLFX_JMA_EEW,
    "global_quake": DataSource.GLOBAL_QUAKE,
    # 地震情报数据源
    "cenc_fanstudio": DataSource.FAN_STUDIO_CENC,
    "cenc_wolfx": DataSource.WOLFX_CENC_EQ,
    "jma_p2p_info": DataSource.P2P_EARTHQUAKE,
    "jma_wolfx_info": DataSource.WOLFX_JMA_EQ,
    "usgs_fanstudio": DataSource.FAN_STUDIO_USGS,
    # 其他数据源
    "china_weather_fanstudio": DataSource.FAN_STUDIO_WEATHER,
    "china_tsunami_fanstudio": DataSource.FAN_STUDIO_TSUNAMI,
    "jma_tsunami_p2p": DataSource.P2P_TSUNAMI,
}


def get_data_source_from_id(new_id: str) -> DataSource | None:
    """从数据源ID获取DataSource枚举值"""
    return DATA_SOURCE_MAPPING.get(new_id)


@dataclass
class EarthquakeData:
    """地震数据 - 增强版本"""

    id: str
    event_id: str
    source: DataSource
    disaster_type: DisasterType

    # 基本信息
    shock_time: datetime
    latitude: float
    longitude: float

    # 位置信息
    place_name: str

    # 有默认值的字段（必须放在后面）
    depth: float | None = None
    magnitude: float | None = None

    # 烈度/震度信息
    intensity: float | None = None  # 中国烈度
    scale: float | None = None  # 日本震度
    max_intensity: float | None = None  # 最大烈度/震度
    max_scale: float | None = None  # P2P数据源的最大震度值

    # 位置信息
    province: str | None = None

    # 更新信息
    updates: int = 1
    is_final: bool = False
    is_cancel: bool = False

    # 其他信息
    info_type: str = ""  # 测定类型：自动/正式等
    domestic_tsunami: str | None = None
    foreign_tsunami: str | None = None

    # 媒体资源
    image_uri: str | None = None  # 地震报告图片
    shakemap_uri: str | None = None  # 等震度图

    # 时间信息（用于不同数据源）
    update_time: datetime | None = None  # 更新时间（USGS等数据源）
    create_time: datetime | None = None  # 创建时间（CWA等数据源）

    # 新增字段 - 适配架构
    source_id: str = ""  # 数据源ID，如"cea_fanstudio"
    report_num: int | None = None  # 报数（某些数据源使用）
    serial: str | None = None  # 序列号（P2P数据源）
    is_training: bool = False  # 是否为训练模式
    is_assumption: bool = False  # 是否为推定震源 (PLUM法)
    is_sea: bool = False  # 是否为海域地震
    revision: Any | None = None  # 修订版本或订正信息
    max_pga: float | None = None  # 最大加速度 (gal)
    stations: dict[str, int] | None = None  # 测站信息 (total, used 等)

    # 原始数据
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.shock_time, str):
            self.shock_time = datetime.fromisoformat(
                self.shock_time.replace("Z", "+00:00")
            )

        # 如果提供了新的source_id，自动映射到DataSource枚举
        if self.source_id and not isinstance(self.source, DataSource):
            mapped_source = get_data_source_from_id(self.source_id)
            if mapped_source:
                self.source = mapped_source


@dataclass
class TsunamiData:
    """海啸数据 - 增强版本"""

    id: str
    code: str
    source: DataSource
    title: str
    level: str  # 黄色、橙色、红色、解除

    # 默认值的字段（必须放在后面）
    disaster_type: DisasterType = DisasterType.TSUNAMI
    subtitle: str | None = None
    org_unit: str = ""

    # 时间信息
    issue_time: datetime | None = None

    # 预报区域
    forecasts: list[dict[str, Any]] = field(default_factory=list)

    # 监测站信息
    monitoring_stations: list[dict[str, Any]] = field(default_factory=list)

    # 新增字段
    source_id: str = ""  # 数据源ID
    estimated_arrival_time: str | None = None  # 预计到达时间
    max_wave_height: str | None = None  # 最大波高

    # 原始数据
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class WeatherAlarmData:
    """气象预警数据 - 增强版本"""

    id: str
    source: DataSource
    headline: str
    title: str
    description: str
    type: str  # 预警类型编码
    effective_time: datetime

    # 默认值的字段
    disaster_type: DisasterType = DisasterType.WEATHER_ALARM
    issue_time: datetime | None = None
    longitude: float | None = None
    latitude: float | None = None

    # 新增字段
    source_id: str = ""  # 数据源ID
    alert_level: str | None = None  # 警报级别
    affected_areas: list[str] = field(default_factory=list)  # 受影响区域

    # 原始数据
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class DisasterEvent:
    """统一灾害事件格式 - 增强版本"""

    id: str
    data: Any  # EarthquakeData, TsunamiData, WeatherAlarmData
    source: DataSource
    disaster_type: DisasterType
    receive_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # 新增字段
    source_id: str = ""  # 数据源ID
    processing_time: datetime | None = None  # 处理时间
    is_filtered: bool = False  # 是否被过滤
    filter_reason: str = ""  # 过滤原因
    push_count: int = 0  # 推送次数

    # 原始数据
    raw_data: dict[str, Any] = field(default_factory=dict)


# 辅助函数
def create_earthquake_data(
    source_id: str, event_data: dict[str, Any], **kwargs
) -> EarthquakeData:
    """创建地震数据的便捷函数"""

    # 获取数据源枚举
    data_source = get_data_source_from_id(source_id)
    if not data_source:
        raise ValueError(f"未知的数据源ID: {source_id}")

    # 确定灾害类型
    if "eew" in source_id or source_id in ["jma_p2p", "jma_wolfx", "global_quake"]:
        disaster_type = DisasterType.EARTHQUAKE_WARNING
    else:
        disaster_type = DisasterType.EARTHQUAKE

    # 创建基础数据
    earthquake_data = EarthquakeData(
        id=event_data.get("id", ""),
        event_id=event_data.get("event_id", event_data.get("id", "")),
        source=data_source,
        disaster_type=disaster_type,
        shock_time=kwargs.get("shock_time", datetime.now(timezone.utc)),
        latitude=kwargs.get("latitude", 0.0),
        longitude=kwargs.get("longitude", 0.0),
        place_name=kwargs.get("place_name", ""),
        source_id=source_id,
        **kwargs,
    )

    return earthquake_data


def validate_earthquake_data(earthquake: EarthquakeData) -> bool:
    """验证地震数据的有效性"""

    # 检查必需字段
    if not earthquake.id or not earthquake.event_id:
        return False

    if earthquake.latitude is None or earthquake.longitude is None:
        return False

    if not earthquake.place_name:
        return False

    # 检查数值范围
    if earthquake.magnitude is not None:
        if earthquake.magnitude < 0 or earthquake.magnitude > 10:
            return False

    if earthquake.depth is not None:
        if earthquake.depth < 0 or earthquake.depth > 800:
            return False

    if earthquake.intensity is not None:
        if earthquake.intensity < 1 or earthquake.intensity > 12:
            return False

    if earthquake.scale is not None:
        if earthquake.scale < 0 or earthquake.scale > 7:
            return False

    return True
