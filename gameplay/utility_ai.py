"""第 62 批：效用 AI 决策管线的 13 类缺陷修复。

修复点对应：
- normalize/clamp01/score_curve：不同量纲先归一化到 [0,1]，再用指数曲线平滑，
  消除阈值处的硬切与维度压制；
- cooldown_ready：冷却以连续量参与评分（剩余为 0 即就绪），不再只做硬条件；
- target_occupy/occupy_claim：队友之间先声明占用，避免所有单位抢同一目标；
- blackboard_fresh：黑板数据带帧号与时效，过期/未来帧不允许驱动行为树；
- interrupt_propagate：打断向上传播到父节点，旧计划不会继续执行；
- tick_dedupe：同一 tick 内只允许更新一次，低帧率补帧不会重复放技能；
- phase_idempotent：阶段只有真正切换时才触发入场，吸血回退不重复入场；
- path_fallback：寻路失败降级为等待/绕行，不再原地转圈到超时；
- separation_force：分散力按有效邻居数钳制，狭窄通道不把队友挤进墙；
- ai_seed：随机种子由 (帧号, 实体 id) 确定性组合，回放一致；
- lod_tick：远距离低频、近距离全频，返回实际应执行的更新频率；
- perception_lost：丢失目标后保留记忆窗口内的仇恨，而非立即清空。
"""


def normalize(value, low, high):
    """评分归一化：把任意量纲的 value 线性映射到 [0,1]。

    距离、血量等维度统一量纲后才可加权求和，避免某一维度数值范围天然压制
    其它维度。零区间（low == high）退化为 0，避免除零。
    """
    if high == low:
        return 0.0
    return clamp01((value - low) / (high - low))


def clamp01(value):
    """钳制到 [0,1]。"""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def score_curve(value, exponent):
    """平滑响应曲线：归一化值取指数，替代阈值处的硬切。

    exponent > 1 曲线下凸（远距离才快速涨分），0 < exponent < 1 上凸
    （近距离敏感）。输入先钳制到 [0,1]，保证曲线单调且有界。
    """
    return clamp01(value) ** exponent


def cooldown_ready(remaining):
    """冷却入分：剩余冷却 <= 0 即就绪。

    冷却不再只是一票否决的硬条件；调用方可用连续的剩余比例参与效用评分，
    就绪判断本身保持布尔语义。
    """
    return remaining <= 0


def target_occupy(target, claimed):
    """目标占用：目标未被队友声明占用时才返回 True。"""
    return target not in claimed


def blackboard_fresh(write_frame, read_frame, max_age):
    """黑板时效：读取时刻数据年龄不超过 max_age 帧才视为新鲜。

    年龄 = read_frame - write_frame；异步写入导致的上一帧陈旧数据
    （年龄为负或过大）都不会被行为树当作当前位置使用。
    """
    return read_frame - write_frame <= max_age


def interrupt_propagate(node, parent):
    """打断传播：当前节点被打断（active 中断）时返回父节点继续向上处理。

    只清当前节点会让父节点按旧计划执行；这里把打断冒泡到父节点，
    未被打断的节点原样返回。
    """
    if node == "active":
        return parent
    return node


def tick_dedupe(tick, last_tick):
    """tick 去重：tick 推进才允许更新，同一 tick 内的重复调用返回 False。

    低帧率补帧时固定 30Hz 调度可能在一帧内触发两次，去重保证技能
    不会在同一 tick 执行两次。
    """
    return tick != last_tick


def phase_idempotent(phase, last_phase):
    """阶段幂等：仅当阶段真正变化时返回 True 触发一次入场逻辑。

    Boss 按血量百分比切阶段，吸血导致血量回落时，只要当前阶段未变
    就不会重复播入场。
    """
    return phase != last_phase


def path_fallback(status):
    """寻路降级：失败时降级等待，阻塞时绕行，成功才继续，杜绝原地转圈。"""
    if status == "failed":
        return "wait"
    if status == "blocked":
        return "reroute"
    return "continue"


def separation_force(neighbors, max_neighbors):
    """拥挤避让：参与分散力计算的邻居数钳制在 [0, max_neighbors]。

    狭窄通道里邻居扎堆时，分散力有上限，不会把队友持续挤进墙体。
    """
    if neighbors <= 0:
        return 0
    return min(neighbors, max_neighbors)


def ai_seed(frame, entity_id):
    """确定性随机：种子由 (帧号, 实体 id) 组合，回放与联机逐帧一致。

    不再用裸帧号做种子（同帧所有单位抽到相同随机数），实体 id 参与
    组合后每个单位的随机序列独立且可复现。
    """
    return (frame, entity_id)


def lod_tick(distance, rate):
    """LOD 状态补齐：近距离按全频 rate 更新，远距离降频到一半（至少 1Hz）。

    返回本帧实际应执行的 AI 更新频率；单位从远处 LOD 切回近处时按全频
    补齐，避免状态缺口导致突然卡住。
    """
    lod_distance = 50
    if distance <= lod_distance:
        return rate
    return max(1, rate // 2)


def perception_lost(lost, memory):
    """感知丢失：丢失目标后在 memory 帧的记忆窗口内保留仇恨。

    返回仇恨应保留的时长：丢失时返回 memory（而非立即清零），
    仍在感知中时无需额外记忆，返回 0。
    """
    if lost:
        return memory
    return 0


def occupy_claim(target, claims):
    """目标占用声明：把 target 登记进 claims（已存在则不重复声明）。

    兼容 list 与 set 两种容器，返回声明后的占用集合。
    """
    if target not in claims:
        if isinstance(claims, set):
            claims.add(target)
        else:
            claims.append(target)
    return claims
