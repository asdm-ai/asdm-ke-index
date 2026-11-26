<div align="center">

# ASDM KE Index

**让 AI 读懂企业十年旧系统，接手它的每一次迭代**

KE（存量系统认知引擎）的公开基准

[English](README.md) | 简体中文

![许可证: Apache 2.0](https://img.shields.io/badge/%E8%AE%B8%E5%8F%AF%E8%AF%81-Apache%202.0-blue?style=flat-square) ![基线: 2026-11-26](https://img.shields.io/badge/%E5%9F%BA%E7%BA%BF-2026--11--26-green?style=flat-square) ![系统: 41](https://img.shields.io/badge/%E7%B3%BB%E7%BB%9F-41-blue?style=flat-square) ![代码行数: 2,491 万](https://img.shields.io/badge/%E4%BB%A3%E7%A0%81%E8%A1%8C%E6%95%B0-2%2C491%20%E4%B8%87-blue?style=flat-square) ![对象: 117 万](https://img.shields.io/badge/%E5%AF%B9%E8%B1%A1-117%20%E4%B8%87-blue?style=flat-square) ![参考线: 6 条](https://img.shields.io/badge/%E5%8F%82%E8%80%83%E7%BA%BF-6%20%E6%9D%A1-blue?style=flat-square)

</div>

---

[参考线](#参考线) · [数据规模与覆盖](#数据规模与覆盖) · [怎么用](#怎么用) · [复核方式](#数据怎么来的怎么复核) · [适用范围](#适用范围)

| 系统 | 代码行数 | 参考线 | 基线 |
|---|---|---|---|
| **41 个开源系统** | **2,491 万行** | **6 条** | **2026-11-26** |

## 它解决什么问题

AI 写代码已经很快，读懂一个维护了十年的系统却依然很慢。要让 AI 安全地接手旧系统的迭代，需要先回答三个问题：这个系统的结构有多纠缠？一处改动会波及哪里？它的质量处在什么水平？

KE 用知识图谱和影响面分析回答前两个问题。KE Index 回答第三个：它让 41 个知名开源 Java 系统跑过同一套引擎，把结果做成一把公开、可复核的尺子。你的系统接入之后，量出来的位置就有了参照。

读者是负责核心系统现代化的架构团队、正在大规模引入 AI 编码工具的研发组织，以及需要向管理层说明系统健康度的技术负责人。

## KE 能测什么

| 能力 | 回答的问题 | 参考线 |
|---|---|---|
| 读懂结构 | 模块之间的依赖有多纠缠 | 循环依赖密度、包依赖密度 |
| 看清质量 | 代码有多难改、测试有多少 | 巨型类占比、圈复杂度 P90、测试方法占比、巨型方法占比 |

当前发布的 6 条参考线全部针对后端 Java 代码。口径与原始数值见 [docs/METRICS_zh-cn.md](docs/METRICS_zh-cn.md)。

## 参考线

> 样本：41 个系统中的 33 个（其余 8 个为 7 个前端工程和 1 个没有 Java 包结构的仓）。基线：2026-11-26。复核方式见[数据怎么来的](#数据怎么来的怎么复核)。

| 指标 | 衡量什么 | 方向 | P25 | 中位数（P50） | P75 |
|---|---|---|---|---|---|
| 循环依赖密度 | 处在循环依赖中的包占全部包的比例（两个及以上的包互相可达即为成环） | 越低越好 | 9.1% | 21.3% | 42.2% |
| 包依赖密度 | 包与包之间的依赖边数除以包数 | 区间型 | 2.3617 | 4.6343 | 7.6102 |
| 巨型类占比 | 超过 500 行的类占全部类的比例 | 越低越好 | 0.62% | 2.5% | 3.6% |
| 圈复杂度 P90 | 90% 的方法圈复杂度不超过该值（在有圈复杂度取值的方法上取第 90 百分位） | 越低越好 | 2 | 3 | 3 |
| 测试方法占比 | 测试方法占全部方法的比例 | 越高越好 | 0.43% | 4.0% | 16.7% |
| 巨型方法占比 | 超过 80 行的方法占有行数记录的方法的比例 | 越低越好 | 0.14% | 0.30% | 0.73% |

中位数把样本分成两半，P25 到 P75 覆盖中间一半的系统。"越低越好"的指标，你的值高于 P75，说明比四分之三的样本更严重。区间型指标不设优劣方向，落在 P25 到 P75 之间属于常见范围。

## 数据规模与覆盖

下表每个系统都由 KE 引擎实际扫描，没有任何数字取自第三方统计。对象与链接是 KE 为该系统构建的知识图谱中的节点与关系；文件数与行数取自所扫描提交上的源码树（行数为物理行，含注释与空行）。

41 个系统按 [repos.yaml](repos.yaml) 的顺序列出。

| # | 仓库 | 类型 | 对象 | 链接 | 文件数 | Java 文件 | 行数 | Java 行数 |
|---|---|---|---|---|---|---|---|---|
| 1 | [macrozheng/mall](https://github.com/macrozheng/mall) | 业务系统 | 14,527 | 35,226 | 717 | 524 | 155,807 | 85,434 |
| 2 | [macrozheng/mall-swarm](https://github.com/macrozheng/mall-swarm) | 业务系统 | 14,878 | 36,007 | 782 | 533 | 158,492 | 87,880 |
| 3 | [yangzongzhuan/RuoYi-Vue](https://github.com/yangzongzhuan/RuoYi-Vue) | 业务系统 | 2,560 | 7,765 | 334 | 266 | 43,618 | 34,332 |
| 4 | [dromara/RuoYi-Vue-Plus](https://github.com/dromara/RuoYi-Vue-Plus) | 业务系统 | 4,777 | 22,903 | 980 | 766 | 113,995 | 83,151 |
| 5 | [jeecgboot/JeecgBoot](https://github.com/jeecgboot/JeecgBoot) | 业务系统 | 15,697 | 116,780 | 4,020 | 995 | 803,350 | 136,494 |
| 6 | [lenve/vhr](https://github.com/lenve/vhr) | 业务系统 | 991 | 1,436 | 242 | 91 | 20,328 | 5,581 |
| 7 | [YunaiV/ruoyi-vue-pro](https://github.com/YunaiV/ruoyi-vue-pro) | 业务系统 | 46,623 | 230,904 | 9,710 | 8,161 | 1,024,622 | 798,916 |
| 8 | [yangzongzhuan/RuoYi-Cloud](https://github.com/yangzongzhuan/RuoYi-Cloud) | 业务系统 | 2,532 | 8,741 | 407 | 274 | 43,949 | 32,652 |
| 9 | [pig-mesh/pig](https://github.com/pig-mesh/pig) | 业务系统 | 2,546 | 7,737 | 708 | 563 | 61,689 | 49,370 |
| 10 | [newbee-ltd/newbee-mall](https://github.com/newbee-ltd/newbee-mall) | 业务系统 | 933 | 1,470 | 318 | 88 | 118,606 | 7,609 |
| 11 | [stylefeng/Guns](https://github.com/stylefeng/Guns) | 业务系统 | 1,377 | 10,042 | 406 | 18 | 60,821 | 1,210 |
| 12 | [renrenio/renren-fast](https://github.com/renrenio/renren-fast) | 业务系统 | 777 | 3,326 | 223 | 143 | 39,002 | 8,821 |
| 13 | [thinkgem/jeesite](https://github.com/thinkgem/jeesite) | 业务系统 | 2,670 | 14,623 | 845 | 0 | 92,527 | 0 |
| 14 | [o2oa/o2oa](https://github.com/o2oa/o2oa) | 业务系统 | 70,501 | 710,059 | 27,933 | 7,824 | 2,751,818 | 773,636 |
| 15 | [chillzhuang/SpringBlade](https://github.com/chillzhuang/SpringBlade) | 业务系统 | 1,073 | 3,002 | 423 | 258 | 34,554 | 17,484 |
| 16 | [dromara/dante-cloud](https://github.com/dromara/dante-cloud) | 业务系统 | 476 | 728 | 892 | 77 | 144,080 | 5,737 |
| 17 | [linlinjava/litemall](https://github.com/linlinjava/litemall) | 业务系统 | 13,172 | 34,102 | 1,591 | 333 | 227,993 | 116,435 |
| 18 | [metersphere/metersphere](https://github.com/metersphere/metersphere) | 业务系统 | 43,718 | 157,807 | 4,716 | 2,706 | 860,678 | 372,881 |
| 19 | [apache/dubbo](https://github.com/apache/dubbo) | 大型多模块 | 34,065 | 136,879 | 4,861 | 4,060 | 524,398 | 484,107 |
| 20 | [apache/fineract](https://github.com/apache/fineract) | 大型多模块 | 54,054 | 266,418 | 9,115 | 7,647 | 1,538,051 | 1,005,293 |
| 21 | [apache/rocketmq](https://github.com/apache/rocketmq) | 大型多模块 | 26,486 | 109,906 | 2,805 | 2,318 | 437,047 | 401,952 |
| 22 | [alibaba/nacos](https://github.com/alibaba/nacos) | 大型多模块 | 57,387 | 435,556 | 7,382 | 5,442 | 1,320,342 | 849,146 |
| 23 | [apache/shardingsphere](https://github.com/apache/shardingsphere) | 大型多模块 | 56,172 | 447,822 | 17,467 | 9,916 | 1,501,418 | 836,710 |
| 24 | [spring-projects/spring-boot](https://github.com/spring-projects/spring-boot) | 大型多模块 | 65,047 | 141,756 | 11,620 | 8,443 | 922,863 | 752,549 |
| 25 | [spring-projects/spring-framework](https://github.com/spring-projects/spring-framework) | 大型多模块 | 105,969 | 286,288 | 11,402 | 9,244 | 1,595,393 | 1,430,520 |
| 26 | [alibaba/druid](https://github.com/alibaba/druid) | 大型多模块 | 41,208 | 234,102 | 6,740 | 5,359 | 702,517 | 598,992 |
| 27 | [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic) | JPA 企业应用 | 283 | 626 | 131 | 50 | 27,644 | 4,297 |
| 28 | [elunez/eladmin](https://github.com/elunez/eladmin) | JPA 企业应用 | 1,357 | 5,096 | 305 | 274 | 26,578 | 23,267 |
| 29 | [keycloak/keycloak](https://github.com/keycloak/keycloak) | JPA 企业应用 | 92,061 | 499,683 | 13,527 | 8,712 | 1,850,827 | 1,309,630 |
| 30 | [flowable/flowable-engine](https://github.com/flowable/flowable-engine) | JPA 企业应用 | 76,265 | 215,262 | 16,202 | 8,082 | 1,730,889 | 1,086,948 |
| 31 | [Activiti/Activiti](https://github.com/Activiti/Activiti) | JPA 企业应用 | 24,203 | 85,736 | 5,387 | 3,095 | 476,182 | 353,553 |
| 32 | [hibernate/hibernate-orm](https://github.com/hibernate/hibernate-orm) | JPA 企业应用 | 180,951 | 421,035 | 21,338 | 19,251 | 2,483,974 | 2,312,508 |
| 33 | [dhis2/dhis2-core](https://github.com/dhis2/dhis2-core) | JPA 企业应用 | 63,457 | 411,972 | 10,299 | 6,670 | 1,621,862 | 1,289,926 |
| 34 | [BroadleafCommerce/BroadleafCommerce](https://github.com/BroadleafCommerce/BroadleafCommerce) | JPA 企业应用 | 25,682 | 108,282 | 3,866 | 2,983 | 563,954 | 353,597 |
| 35 | [macrozheng/mall-admin-web](https://github.com/macrozheng/mall-admin-web) | 前端工程 | 1,662 | 29,228 | 358 | 0 | 36,098 | 0 |
| 36 | [yangzongzhuan/RuoYi-Vue3](https://github.com/yangzongzhuan/RuoYi-Vue3) | 前端工程 | 1,078 | 6,243 | 281 | 0 | 26,397 | 0 |
| 37 | [jeecgboot/jeecgboot-vue3](https://github.com/jeecgboot/jeecgboot-vue3) | 前端工程 | 4,755 | 25,600 | 1,424 | 0 | 173,262 | 0 |
| 38 | [pig-mesh/pig-ui](https://github.com/pig-mesh/pig-ui) | 前端工程 | 1,974 | 11,417 | 479 | 0 | 59,233 | 0 |
| 39 | [yudaocode/yudao-ui-admin-vue3](https://github.com/yudaocode/yudao-ui-admin-vue3) | 前端工程 | 16,456 | 3,065,439 | 3,274 | 0 | 509,620 | 0 |
| 40 | [elunez/eladmin-web](https://github.com/elunez/eladmin-web) | 前端工程 | 538 | 1,133 | 279 | 0 | 18,332 | 0 |
| 41 | [newbee-ltd/newbee-mall-vue3-app](https://github.com/newbee-ltd/newbee-mall-vue3-app) | 前端工程 | 181 | 382 | 59 | 0 | 10,854 | 0 |
| | **合计（41 个）** | | **1,171,119** | **8,348,519** | **203,848** | **125,166** | **24,913,664** | **15,710,618** |

- **业务系统（18）**：Java 脚手架与业务系统，以及电商、办公、工具类业务系统
- **大型多模块（8）**：超大型多模块仓库：Apache 系中间件与 Spring 生态基石
- **JPA 企业应用（8）**：JPA 形态的系统：IAM / BPM / ERP 应用与 JPA 实现本体
- **前端工程（7）**：业务系统的官方前端仓库（Vue 系）

**跨度。** 这些系统的代码规模从 10,854 行到 2,751,818 行（中位数 173,262 行），图谱对象从 181 个到 180,951 个。

**现在的覆盖范围与目标。** 41 个系统的规模还不足以代表整个开源社区的状态。语料在逐步扩展，目标是达到具备统计学价值的样本比例。在此之前，参考线反映的是这批语料的状况。

**有一处链接数尚未查明原因。**yudaocode/yudao-ui-admin-vue3 一个系统就占全部链接的约 37%（对象 16,456 个、链接 3,065,439 条，约每个对象 186 条，远高于其它系统）。原因尚未查明，见 [docs/CORPUS_zh-cn.md](docs/CORPUS_zh-cn.md)。

源码版本、快照与逐仓明细见 [docs/CORPUS_zh-cn.md](docs/CORPUS_zh-cn.md)。

## 怎么用

1. 在 [kengine.ai](https://kengine.ai) 接入你的系统仓库。
2. 引擎构建知识图谱并计算指标。
3. 把你的数值对照上面的参考线，看它处在什么位置。

参考线随每次重扫更新，对照时请以本页标注的基线日期为准。

## 数据怎么来的、怎么复核

- **同一版本的分析器。** 41 个系统全部由同一版本的分析器度量。
- **全部通过管线。** 扫描、图谱构建、指标计算、一致性比对四个环节 41/41 通过，失败 0 个，无缺失。
- **已复核的参考线。**巨型类占比、圈复杂度 P90、测试方法占比、巨型方法占比：分子或分母逐仓与服务端按条件另查一次的结果比对，每条都是 33/33 一致。
- **尚无独立复核的参考线。**循环依赖密度、包依赖密度由包依赖清单一次算出，目前没有第二道核对。
- **文件数。** 逐仓与服务端的文件数比对，41/41 一致。
- **可以自己核对。** 逐仓报告、管线结论和聚合数据都在本仓库（`reports/`、`pipeline-status/`、`census/`），方法见 [docs/PIPELINE_zh-cn.md](docs/PIPELINE_zh-cn.md)。
- **每月刷新。** 每月 1 日刷新基线：上游有新提交的系统重新扫描，其余保持上一次的测量结果。[本次基线的运行记录](https://github.com/asdm-ai/asdm-ke-index/actions/runs/45829165719)：2026-11-26 13:26–18:13 UTC，用时 4h 46m 57s。

## 适用范围

1. **是精选样本，不是随机抽样。** 语料是知名 Java 仓库的分层选取，存在自选择偏差。参考线不是行业普查，也不是行业基准。
2. **只覆盖全库整体。** 每条参考线覆盖全部 33 个系统；目前没有任何一个类型达到 30 个系统，所以没有分类型的参考线。
3. **只覆盖后端 Java。** 前端工程只参与规模统计。
4. **有 3 个系统在当前版本上 Java 代码很少**（stylefeng/Guns、thinkgem/jeesite、dromara/dante-cloud），对参考线的代表性有限。
5. **行数是物理行**，含注释与空行，不是 SLOC。口径见 [docs/CORPUS_zh-cn.md](docs/CORPUS_zh-cn.md)。
6. **单一时间点。** 基线是一个横截面，随每次刷新更新。

## 许可与引用

- 许可证：[Apache License 2.0](LICENSE)。
- 引用格式：ASDM KE Index，基线 run #36（`45829165719`），2026-11-26。
- 语料：全部系统都是开源项目，版权归各自作者。本仓库只发布计数与指标数值，不含语料的源代码。
- 反馈：[Issues](https://github.com/asdm-ai/asdm-ke-index/issues)。
