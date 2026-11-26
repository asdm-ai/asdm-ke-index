# 语料：逐仓明细

[English](CORPUS.md) | 简体中文

[参考线](../README_zh-cn.md)背后的全部仓库，含快照、规模与管线结论。基线 2026-11-26，run #36（`45829165719`）。

## 分层

| 分层 | 仓数 | 形态 |
|---|---|---|
| A · 业务系统 | 18 | Java 脚手架与业务系统：RuoYi 系、Jeecg、芋道、Pig 等，以及电商、办公、工具类业务系统 |
| B · 大型多模块 | 8 | 超大型多模块仓库，以 Gradle 为主：Apache 系中间件与 Spring 生态基石 |
| C · JPA 企业应用 | 8 | JPA 形态的系统：IAM / BPM / ERP 应用与 hibernate-orm 本体 |
| D · 前端工程 | 7 | 业务系统的官方前端仓库（Vue 系） |

> 全量清单见 [repos.yaml](../repos.yaml)。快照 ID 截取前 8 位（完整值见 `census/summary.json` 的 repos 区）。

## 全部仓库

| # | owner/repo | 分层 | 快照 | 源码版本 | 报告 | 对象数 | 链接数 | 文件数 | Java 文件 | 行数 | Java 行数 | 管线 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | [macrozheng/mall](https://github.com/macrozheng/mall) | A | `104877ef` | `dcaa93b3` | [report](../reports/macrozheng/mall.json) | 14,527 | 35,226 | 717 | 524 | 155,807 | 85,434 | ✅ |
| 2 | [macrozheng/mall-swarm](https://github.com/macrozheng/mall-swarm) | A | `867c82e8` | `04c442fe` | [report](../reports/macrozheng/mall-swarm.json) | 14,878 | 36,007 | 782 | 533 | 158,492 | 87,880 | ✅ |
| 3 | [yangzongzhuan/RuoYi-Vue](https://github.com/yangzongzhuan/RuoYi-Vue) | A | `756caa24` | `c61d958a` | [report](../reports/yangzongzhuan/RuoYi-Vue.json) | 2,560 | 7,765 | 334 | 266 | 43,618 | 34,332 | ✅ |
| 4 | [dromara/RuoYi-Vue-Plus](https://github.com/dromara/RuoYi-Vue-Plus) | A | `a3e8b577` | `835246eb` | [report](../reports/dromara/RuoYi-Vue-Plus.json) | 4,777 | 22,903 | 980 | 766 | 113,995 | 83,151 | ✅ |
| 5 | [jeecgboot/JeecgBoot](https://github.com/jeecgboot/JeecgBoot) | A | `3f1b932d` | `6184e244` | [report](../reports/jeecgboot/JeecgBoot.json) | 15,697 | 116,780 | 4,020 | 995 | 803,350 | 136,494 | ✅ |
| 6 | [lenve/vhr](https://github.com/lenve/vhr) | A | `a359e4fa` | `28a9f8a5` | [report](../reports/lenve/vhr.json) | 991 | 1,436 | 242 | 91 | 20,328 | 5,581 | ✅ |
| 7 | [YunaiV/ruoyi-vue-pro](https://github.com/YunaiV/ruoyi-vue-pro) | A | `2249ebcd` | `e34c0f22` | [report](../reports/YunaiV/ruoyi-vue-pro.json) | 46,623 | 230,904 | 9,710 | 8,161 | 1,024,622 | 798,916 | ✅ |
| 8 | [yangzongzhuan/RuoYi-Cloud](https://github.com/yangzongzhuan/RuoYi-Cloud) | A | `e7f1c4d0` | `5db048bb` | [report](../reports/yangzongzhuan/RuoYi-Cloud.json) | 2,532 | 8,741 | 407 | 274 | 43,949 | 32,652 | ✅ |
| 9 | [pig-mesh/pig](https://github.com/pig-mesh/pig) | A | `3d9872f0` | `0d57d08f` | [report](../reports/pig-mesh/pig.json) | 2,546 | 7,737 | 708 | 563 | 61,689 | 49,370 | ✅ |
| 10 | [newbee-ltd/newbee-mall](https://github.com/newbee-ltd/newbee-mall) | A | `fad84fb5` | `a069069b` | [report](../reports/newbee-ltd/newbee-mall.json) | 933 | 1,470 | 318 | 88 | 118,606 | 7,609 | ✅ |
| 11 | [stylefeng/Guns](https://github.com/stylefeng/Guns) | A ⚠️ | `9dda3f5a` | `2a129477` | [report](../reports/stylefeng/Guns.json) | 1,377 | 10,042 | 406 | 18 | 60,821 | 1,210 | ✅ |
| 12 | [renrenio/renren-fast](https://github.com/renrenio/renren-fast) | A | `41ba483e` | `75148ab5` | [report](../reports/renrenio/renren-fast.json) | 777 | 3,326 | 223 | 143 | 39,002 | 8,821 | ✅ |
| 13 | [thinkgem/jeesite](https://github.com/thinkgem/jeesite) | A ⚠️ | `77063f14` | `ba594847` | [report](../reports/thinkgem/jeesite.json) | 2,670 | 14,623 | 845 | 0 | 92,527 | 0 | ✅ |
| 14 | [o2oa/o2oa](https://github.com/o2oa/o2oa) | A | `c19b3102` | `8ce6a68c` | [report](../reports/o2oa/o2oa.json) | 70,501 | 710,059 | 27,933 | 7,824 | 2,751,818 | 773,636 | ✅ |
| 15 | [chillzhuang/SpringBlade](https://github.com/chillzhuang/SpringBlade) | A | `779fd2e5` | `4995ddb7` | [report](../reports/chillzhuang/SpringBlade.json) | 1,073 | 3,002 | 423 | 258 | 34,554 | 17,484 | ✅ |
| 16 | [dromara/dante-cloud](https://github.com/dromara/dante-cloud) | A ⚠️ | `2cdd68f7` | `c0402026` | [report](../reports/dromara/dante-cloud.json) | 476 | 728 | 892 | 77 | 144,080 | 5,737 | ✅ |
| 17 | [linlinjava/litemall](https://github.com/linlinjava/litemall) | A | `4de8e93f` | `a1ef964a` | [report](../reports/linlinjava/litemall.json) | 13,172 | 34,102 | 1,591 | 333 | 227,993 | 116,435 | ✅ |
| 18 | [metersphere/metersphere](https://github.com/metersphere/metersphere) | A | `a5733632` | `f1565d99` | [report](../reports/metersphere/metersphere.json) | 43,718 | 157,807 | 4,716 | 2,706 | 860,678 | 372,881 | ✅ |
| 19 | [apache/dubbo](https://github.com/apache/dubbo) | B | `c170d16e` | `ae46e0a5` | [report](../reports/apache/dubbo.json) | 34,065 | 136,879 | 4,861 | 4,060 | 524,398 | 484,107 | ✅ |
| 20 | [apache/fineract](https://github.com/apache/fineract) | B | `580ff321` | `4d9557a5` | [report](../reports/apache/fineract.json) | 54,054 | 266,418 | 9,115 | 7,647 | 1,538,051 | 1,005,293 | ✅ |
| 21 | [apache/rocketmq](https://github.com/apache/rocketmq) | B | `38fd86d7` | `e114b542` | [report](../reports/apache/rocketmq.json) | 26,486 | 109,906 | 2,805 | 2,318 | 437,047 | 401,952 | ✅ |
| 22 | [alibaba/nacos](https://github.com/alibaba/nacos) | B | `922f4ddb` | `9a5c29a4` | [report](../reports/alibaba/nacos.json) | 57,387 | 435,556 | 7,382 | 5,442 | 1,320,342 | 849,146 | ✅ |
| 23 | [apache/shardingsphere](https://github.com/apache/shardingsphere) | B | `82f2d160` | `03aa12d5` | [report](../reports/apache/shardingsphere.json) | 56,172 | 447,822 | 17,467 | 9,916 | 1,501,418 | 836,710 | ✅ |
| 24 | [spring-projects/spring-boot](https://github.com/spring-projects/spring-boot) | B | `4b21f1bf` | `f580d002` | [report](../reports/spring-projects/spring-boot.json) | 65,047 | 141,756 | 11,620 | 8,443 | 922,863 | 752,549 | ✅ |
| 25 | [spring-projects/spring-framework](https://github.com/spring-projects/spring-framework) | B | `8cdd2ce5` | `309ebb14` | [report](../reports/spring-projects/spring-framework.json) | 105,969 | 286,288 | 11,402 | 9,244 | 1,595,393 | 1,430,520 | ✅ |
| 26 | [alibaba/druid](https://github.com/alibaba/druid) | B | `fe51de02` | `fa8dc991` | [report](../reports/alibaba/druid.json) | 41,208 | 234,102 | 6,740 | 5,359 | 702,517 | 598,992 | ✅ |
| 27 | [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic) | C | `c604adfb` | `500158f7` | [report](../reports/spring-projects/spring-petclinic.json) | 283 | 626 | 131 | 50 | 27,644 | 4,297 | ✅ |
| 28 | [elunez/eladmin](https://github.com/elunez/eladmin) | C | `8389435e` | `646c58c3` | [report](../reports/elunez/eladmin.json) | 1,357 | 5,096 | 305 | 274 | 26,578 | 23,267 | ✅ |
| 29 | [keycloak/keycloak](https://github.com/keycloak/keycloak) | C | `fa090d70` | `d22c7c58` | [report](../reports/keycloak/keycloak.json) | 92,061 | 499,683 | 13,527 | 8,712 | 1,850,827 | 1,309,630 | ✅ |
| 30 | [flowable/flowable-engine](https://github.com/flowable/flowable-engine) | C | `6e898ac7` | `2af890cd` | [report](../reports/flowable/flowable-engine.json) | 76,265 | 215,262 | 16,202 | 8,082 | 1,730,889 | 1,086,948 | ✅ |
| 31 | [Activiti/Activiti](https://github.com/Activiti/Activiti) | C | `385b3aa1` | `012e9920` | [report](../reports/Activiti/Activiti.json) | 24,203 | 85,736 | 5,387 | 3,095 | 476,182 | 353,553 | ✅ |
| 32 | [hibernate/hibernate-orm](https://github.com/hibernate/hibernate-orm) | C | `39412056` | `9c71bdb5` | [report](../reports/hibernate/hibernate-orm.json) | 180,951 | 421,035 | 21,338 | 19,251 | 2,483,974 | 2,312,508 | ✅ |
| 33 | [dhis2/dhis2-core](https://github.com/dhis2/dhis2-core) | C | `0607cfca` | `72e44852` | [report](../reports/dhis2/dhis2-core.json) | 63,457 | 411,972 | 10,299 | 6,670 | 1,621,862 | 1,289,926 | ✅ |
| 34 | [BroadleafCommerce/BroadleafCommerce](https://github.com/BroadleafCommerce/BroadleafCommerce) | C | `42c6eff8` | `0ffc1de7` | [report](../reports/BroadleafCommerce/BroadleafCommerce.json) | 25,682 | 108,282 | 3,866 | 2,983 | 563,954 | 353,597 | ✅ |
| 35 | [macrozheng/mall-admin-web](https://github.com/macrozheng/mall-admin-web) | D | `a9ea2b99` | `81fc17e5` | [report](../reports/macrozheng/mall-admin-web.json) | 1,662 | 29,228 | 358 | 0 | 36,098 | 0 | ✅ |
| 36 | [yangzongzhuan/RuoYi-Vue3](https://github.com/yangzongzhuan/RuoYi-Vue3) | D | `f98278f7` | `3c2b70c3` | [report](../reports/yangzongzhuan/RuoYi-Vue3.json) | 1,078 | 6,243 | 281 | 0 | 26,397 | 0 | ✅ |
| 37 | [jeecgboot/jeecgboot-vue3](https://github.com/jeecgboot/jeecgboot-vue3) | D | `5802e1ef` | `defd8d93` | [report](../reports/jeecgboot/jeecgboot-vue3.json) | 4,755 | 25,600 | 1,424 | 0 | 173,262 | 0 | ✅ |
| 38 | [pig-mesh/pig-ui](https://github.com/pig-mesh/pig-ui) | D | `11e95353` | `ecdb12ba` | [report](../reports/pig-mesh/pig-ui.json) | 1,974 | 11,417 | 479 | 0 | 59,233 | 0 | ✅ |
| 39 | [yudaocode/yudao-ui-admin-vue3](https://github.com/yudaocode/yudao-ui-admin-vue3) | D | `5ddd7597` | `af5d4870` | [report](../reports/yudaocode/yudao-ui-admin-vue3.json) | 16,456 | 3,065,439 | 3,274 | 0 | 509,620 | 0 | ✅ |
| 40 | [elunez/eladmin-web](https://github.com/elunez/eladmin-web) | D | `52df4d82` | `6e20207b` | [report](../reports/elunez/eladmin-web.json) | 538 | 1,133 | 279 | 0 | 18,332 | 0 | ✅ |
| 41 | [newbee-ltd/newbee-mall-vue3-app](https://github.com/newbee-ltd/newbee-mall-vue3-app) | D | `c406ff31` | `07740cba` | [report](../reports/newbee-ltd/newbee-mall-vue3-app.json) | 181 | 382 | 59 | 0 | 10,854 | 0 | ✅ |

## 语料说明

> ⚠️ **分层漂移**：3 个 A 层仓在当前 HEAD 上 `.java` 已不是最大的文件类别（stylefeng/Guns：18 个 `.java` 对 163 个 `.vue`；thinkgem/jeesite：0 个 `.java` 对 409 个 `.typescript`；dromara/dante-cloud：77 个 `.java` 对 637 个 `.sql`）。这些仓仍计入 A 层，但 Java 代码很少。

- **一处待归因的链接数**：yudaocode/yudao-ui-admin-vue3 的对象 16,456 个、链接 3,065,439 条（约每个对象 186 条，远高于其它仓）。

## 仓规模（文件数 / 行数）

仓规模在扫描的同时采集（`scan-one.sh` clone 之后、import 之前，同一工作树同一 HEAD），由 `scripts/repo-scale.py` 完成。它落在各 report 的 `report.metrics.D3.scale`，并在 `census/summary.json` 给出逐仓字段（`repos[]`）与跨仓分布（`cohort.scale`）。作为各指标的规模参照，不参与评分。

### 口径

| 字段 | 口径 |
|---|---|
| 文件数 `fileCount` | tracked 文件数，剔除分析器跳过目录（`target` / `build` / `dist` / `node_modules` 等）与符号链接等非普通文件；与分析器 `Repository.fileCount` 同口径，扫描时逐仓对照（不一致只告警不置红） |
| Java 文件 `javaFiles` | 其中 `.java` 文件数 |
| 总行数 `lineCount` | 文本文件的物理行数，含注释与空行，**不是 SLOC**；二进制文件（首 8000 字节含 NUL）不计 |
| Java 行数 `javaLines` | 其中 `.java` 文件的物理行数 |

### 全库合计

| 指标 | 全部仓合计 | 最小仓 | 最大仓 |
|---|---|---|---|
| 文件数 | 203,848 | 59 | 27,933 |
| Java 文件数 | 125,166 | 0 | 19,251 |
| 总行数 | 24,913,664 | 10,854 | 2,751,818 |
| Java 行数 | 15,710,618 | 0 | 2,312,508 |

Java 占全部计入行数的 63.1%、计入文件数的 61.4%。41 个仓在 git 中共有 204,788 个 tracked 文件（计入文本 185,807 个，判定为二进制并跳过 18,041 个）。

### 跨仓分布

| 指标 | N | 缺失 | Min | P25 | P50 | P75 | P90 | Max | 合计 | 均值 |
|---|---|---|---|---|---|---|---|---|---|---|
| 文件数 `fileCount` | 41 | 0 | 59 | 406 | 1,424 | 7,382 | 13,527 | 27,933 | 203,848 | 4,972 |
| Java 文件数 `javaFiles` | 41 | 0 | 0 | 77 | 533 | 5,442 | 8,443 | 19,251 | 125,166 | 3,053 |
| 总行数 `lineCount` | 41 | 0 | 10,854 | 43,949 | 173,262 | 922,863 | 1,621,862 | 2,751,818 | 24,913,664 | 607,650 |
| Java 行数 `javaLines` | 41 | 0 | 0 | 5,581 | 85,434 | 752,549 | 1,086,948 | 2,312,508 | 15,710,618 | 383,186 |

分位数为 `census/summary.json` 中的最近秩取值。

### 分层对照

| 分层 | 仓数 | 文件数中位 | 行数中位 | Java 行数中位 | Java 行数合计 |
|---|---|---|---|---|---|
| 业务系统 | 18 | 749 | 116,300 | 41,851 | 2,617,623 |
| 大型多模块 | 8 | 8,248 | 1,121,602 | 794,629 | 6,359,269 |
| JPA 企业应用 | 8 | 7,843 | 1,092,908 | 720,272 | 6,733,726 |
| 前端工程 | 7 | 358 | 36,098 | 0 | 0 |

### 规模最大的仓

按 Java 行数：

| 仓库 | Java 行数 | 行数 | Java 文件 | 文件数 |
|---|---|---|---|---|
| [hibernate/hibernate-orm](https://github.com/hibernate/hibernate-orm) | 2,312,508 | 2,483,974 | 19,251 | 21,338 |
| [spring-projects/spring-framework](https://github.com/spring-projects/spring-framework) | 1,430,520 | 1,595,393 | 9,244 | 11,402 |
| [keycloak/keycloak](https://github.com/keycloak/keycloak) | 1,309,630 | 1,850,827 | 8,712 | 13,527 |
| [dhis2/dhis2-core](https://github.com/dhis2/dhis2-core) | 1,289,926 | 1,621,862 | 6,670 | 10,299 |
| [flowable/flowable-engine](https://github.com/flowable/flowable-engine) | 1,086,948 | 1,730,889 | 8,082 | 16,202 |

按总行数：

| 仓库 | Java 行数 | 行数 | Java 文件 | 文件数 |
|---|---|---|---|---|
| [o2oa/o2oa](https://github.com/o2oa/o2oa) | 773,636 | 2,751,818 | 7,824 | 27,933 |
| [hibernate/hibernate-orm](https://github.com/hibernate/hibernate-orm) | 2,312,508 | 2,483,974 | 19,251 | 21,338 |
| [keycloak/keycloak](https://github.com/keycloak/keycloak) | 1,309,630 | 1,850,827 | 8,712 | 13,527 |
| [flowable/flowable-engine](https://github.com/flowable/flowable-engine) | 1,086,948 | 1,730,889 | 8,082 | 16,202 |
| [dhis2/dhis2-core](https://github.com/dhis2/dhis2-core) | 1,289,926 | 1,621,862 | 6,670 | 10,299 |

### 分语言行数

| 语言（按扩展名） | 行数 | 占比 | 文件数 |
|---|---|---|---|
| `java` | 15,710,618 | 63.1% | 125,166 |
| `javascript` | 1,952,331 | 7.8% | 5,818 |
| `other` | 1,593,683 | 6.4% | 30,779 |
| `vue` | 1,028,838 | 4.1% | 5,497 |
| `xml` | 1,012,698 | 4.1% | 13,453 |
| `json` | 882,181 | 3.5% | 2,240 |
| `sql` | 404,530 | 1.6% | 4,431 |
| `html` | 387,821 | 1.6% | 2,016 |
| `typescript` | 371,773 | 1.5% | 4,074 |
| `yaml` | 313,054 | 1.3% | 2,330 |
| 其余（11 种） | 1,256,137 | 5.0% | 8,044 |

- **Java 行数是首要的规模参照。** 总行数会被设计文档、SVG 与生成物抬高：macrozheng/mall 的 `other` 桶（未识别扩展名，这里主要是 `.pdb` / `.pdm` 设计文件）单项就有 41,854 行。
- 分语言明细（`linesByLanguage` / `filesByLanguage`）见各 report。
