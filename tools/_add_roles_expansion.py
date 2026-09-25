"""把扩充的 55 人录入 roles.yaml（生成完成后跑）"""
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "assets/cast/library/roles.yaml"
t = p.read_text(encoding="utf-8")

NAMES = {
    # 核心卡司 +15
    "core_wife_66": ("老王老伴", "女", 66, "花白卷发·深红开衫·慈祥"),
    "core_son_38": ("老王儿子", "男", 38, "黑短发·浅蓝衬衫·稳重微胖"),
    "core_daughter_35": ("老王女儿", "女", 35, "齐肩发·米色风衣·干练温柔"),
    "core_grandson_12": ("老王孙子", "男", 12, "短寸·校服·机灵"),
    "core_granddaughter_8": ("老王孙女", "女", 8, "双马尾·粉卫衣·可爱"),
    "core_dil_33": ("老王儿媳", "女", 33, "马尾·浅灰毛衣·温婉"),
    "core_sil_37": ("老王女婿", "男", 37, "短发·深蓝夹克·斯文"),
    "core_neighbor_li_68": ("邻居老李", "男", 68, "稀疏短发·棕夹克·爱聊"),
    "core_chess_friend_70": ("棋友老周", "男", 70, "白短须·灰马甲·慢悠悠"),
    "core_dance_partner_64": ("舞伴张姨", "女", 64, "黑烫发·红丝巾·爽朗"),
    "core_doctor_45": ("社区医生", "男", 45, "白大褂眼镜·温和"),
    "core_shop_owner_50": ("小卖部老板", "男", 50, "蓝围裙·圆脸和善"),
    "core_nurse_young_26": ("社区护理员", "女", 26, "粉制服·马尾·亲切"),
    "core_old_comrade_72": ("老战友", "男", 72, "银寸头·军绿外套·硬朗"),
    "core_postman_40": ("老邮递员", "男", 40, "灰制服帽·深绿工装·朴实"),
    # 欧美组 +15
    "western_granny_70": ("外国奶奶", "女", 70, "银白短卷·紫开衫老花镜·慈祥"),
    "western_aunt_55": ("外国阿姨", "女", 55, "金发盘髻·米色风衣·优雅"),
    "western_uncle_50": ("外国叔叔", "男", 50, "灰棕短发·卡其夹克·稳健"),
    "western_lady_45": ("外国女士", "女", 45, "栗色中长发·墨绿裙·知性"),
    "western_gent_60": ("外国绅士", "男", 60, "银灰背头·灰三件套·老派"),
    "western_doctor_42": ("外国医生", "男", 42, "深棕短发·白大褂·专业"),
    "western_teacher_38": ("外国教师", "女", 38, "金发bob·驼色针织·温和"),
    "western_chef_35": ("外国厨师", "男", 35, "短发胡茬·白厨服·爽朗"),
    "western_athlete_26": ("外国运动员", "男", 26, "金棕短发·运动T恤·阳光"),
    "western_artist_29": ("外国艺术家", "女", 29, "棕卷发贝雷帽·姜黄毛衣·文艺"),
    "western_businessman_50": ("外国商人", "男", 50, "花白背头·藏蓝西装·商务"),
    "western_neighbor_62": ("外国邻居", "男", 62, "银发微卷·绿polo·随和"),
    "western_teen_boy_16": ("外国少年", "男", 16, "浅金碎发·连帽卫衣·青春"),
    "western_teen_girl_15": ("外国少女", "女", 15, "棕长马尾·白卫衣·活泼"),
    "western_kid_girl_7": ("外国小女孩", "女", 7, "金双马尾·黄裙·萌"),
    # 时尚组 +10
    "fashion_lady_50": ("时尚阿姨", "女", 50, "深棕短发·酒红衬衫·成熟"),
    "fashion_gent_55": ("时尚绅士", "男", 55, "银灰背头·墨绿西装·儒雅"),
    "fashion_girl_20": ("酷甜女孩", "女", 20, "黑短发挑染·oversize西装"),
    "fashion_boy_22": ("文艺男生", "男", 22, "栗棕卷发·米色polo·慵懒"),
    "fashion_woman_32": ("极简姐姐", "女", 32, "黑长直·白廓形衬衫·高级"),
    "fashion_man_35": ("极简先生", "男", 35, "寸头·黑高领·极简"),
    "fashion_granny_2": ("宝蓝奶奶", "女", 70, "银发发夹·宝蓝大衣·矍铄"),
    "fashion_grandpa_2": ("雅士爷爷", "男", 75, "圆顶帽·驼色大衣·慢生活"),
    "fashion_girl_2": ("通勤女孩", "女", 26, "栗色卷发·格纹西装·通勤"),
    "fashion_man_2": ("都市型男", "男", 40, "短发·深灰风衣·型男"),
    # 老外时尚组 +15
    "fashion_western_lady_50": ("老外气场女士", "女", 50, "金发短发·白西装·气场"),
    "fashion_western_gent_55": ("老外品味绅士", "男", 55, "银白后梳·深紫西装·品味"),
    "fashion_western_girl_20": ("老外酷女孩", "女", 20, "黑波波头·银皮衣·酷"),
    "fashion_western_boy_22": ("老外文艺男生", "男", 22, "深金卷发·燕麦针织·清新"),
    "fashion_western_woman_2": ("老外知性姐姐", "女", 32, "红棕长卷·黑大衣·时髦"),
    "fashion_western_man_2": ("老外休闲先生", "男", 35, "深棕短发·深蓝polo·沉稳"),
    "fashion_western_granny_2": ("老外雍容奶奶", "女", 72, "银发盘髻·墨绿丝绒·雍容"),
    "fashion_western_grandpa_2": ("老外英伦爷爷", "男", 74, "白发白须·粗花呢·英伦"),
    "fashion_western_teen_girl_16": ("老外甜美少女", "女", 16, "浅金长直·粉羊羔绒·甜美"),
    "fashion_western_teen_boy_17": ("老外清秀少年", "男", 17, "棕卷发·条纹毛衣·清秀"),
    "fashion_western_kid_girl_8": ("老外红大衣女孩", "女", 8, "金棕双辫·红呢大衣"),
    "fashion_western_kid_boy_9": ("老外精灵男孩", "男", 9, "金短发·海军蓝毛衣"),
    "fashion_western_athlete_26": ("老外活力男", "男", 26, "深金短发·白运动夹克"),
    "fashion_western_artist_29": ("老外艺术女", "女", 29, "深棕编发·橙针织·艺术"),
    "fashion_western_singer_24": ("老外明艳歌手", "女", 24, "黑长卷·银吊带·明艳"),
}

REGION = {
    "core_": "核心卡司", "western_": "欧美", "fashion_western": "老外时尚", "fashion_": "时尚",
}

lines = ["", "  # ── 扩充组（2026-09-25 宝哥令：每组补到20人） ──"]
for rid, (nm, gender, age, trait) in NAMES.items():
    if rid.startswith("fashion_western"):
        region = "老外时尚"
    elif rid.startswith("fashion_"):
        region = "时尚"
    elif rid.startswith("western_"):
        region = "欧美"
    else:
        region = "核心卡司"
    lines.append(f"  - {{id: {rid}, name: {nm}, age: {age}, gender: {gender}, region: {region}, relation: 扩充组, trait: {trait}}}")

if "core_wife_66," not in t:
    t = t.rstrip() + "\n" + "\n".join(lines) + "\n"
    p.write_text(t, encoding="utf-8")
    print(f"✓ 已录入 {len(NAMES)} 人")
else:
    print("已录过，跳过")
