# 中国人口区域分布瓶装图

基于2024年最新统计数据，中国人口在空间分布上呈现显著的区域不均衡性，主要集中在中东部地区。以下是使用Mermaid语法绘制的瓶装图（Barrel Chart），展示主要省份的人口规模对比。

```mermaid
graph TD
    subgraph 中国人口区域分布（单位：万人）
        A[广东省 12859] --> B[山东省 10043]
        B --> C[河南省 9785]
        C --> D[江苏省 8526]
        D --> E[四川省 8364]
        E --> F[河北省 7378]
        F --> G[湖南省 6539]
        G --> H[安徽省 6123]
        H --> I[湖北省 5834]
        I --> J[广西 4989]
        J --> K[云南省 4655]
        K --> L[江西省 4502]
        L --> M[福建省 4193]
        M --> N[辽宁省 4155]
        N --> O[陕西省 3953]
        O --> P[贵州省 3857]
        P --> Q[山西省 3445]
        Q --> R[黑龙江省 3029]
    end

    style A fill:#f9c,stroke:#333,stroke-width:2px
    style B fill:#9cf,stroke:#333,stroke-width:2px
    style C fill:#9cf,stroke:#333,stroke-width:2px
    style D fill:#9cf,stroke:#333,stroke-width:2px
    style E fill:#cf9,stroke:#333,stroke-width:2px
    style F fill:#cf9,stroke:#333,stroke-width:2px
    style G fill:#cf9,stroke:#333,stroke-width:2px
    style H fill:#cf9,stroke:#333,stroke-width:2px
    style I fill:#cf9,stroke:#333,stroke-width:2px
    style J fill:#ccf,stroke:#333,stroke-width:2px
    style K fill:#ccf,stroke:#333,stroke-width:2px
    style L fill:#ccf,stroke:#333,stroke-width:2px
    style M fill:#ccf,stroke:#333,stroke-width:2px
    style N fill:#ccf,stroke:#333,stroke-width:2px
    style O fill:#ccf,stroke:#333,stroke-width:2px
    style P fill:#ccf,stroke:#333,stroke-width:2px
    style Q fill:#ccf,stroke:#333,stroke-width:2px
    style R fill:#ccf,stroke:#333,stroke-width:2px
```

## 数据说明
- 数据来源：基于2024年各省常住人口排名统计（如广东省12859万人、山东省10043万人等）。
- 图表类型：瓶装图（Barrel Chart），通过节点大小和颜色渐变直观展示人口规模差异。
- 区域划分：
  - **粉色节点**：人口超1亿的省份（广东）。
  - **蓝色节点**：人口5000万至1亿的省份（山东、河南、江苏、四川）。
  - **绿色节点**：人口3000万至5000万的省份（河北至湖北）。
  - **淡紫色节点**：人口低于3000万的省份（广西至黑龙江）。

## 主要特点
1. **高度集中**：广东、山东、河南、江苏、四川五省人口合计占全国总人口的约35%。
2. **东西差异**：东部和南方省份人口规模显著高于西部（如西藏、青海等）。
3. **趋势**：人口持续向东部沿海和城市群集聚，东北、西北地区人口呈流出态势。

## 使用建议
- 可将Mermaid代码复制到支持Mermaid的编辑器（如GitHub、Typora、Obsidian）中渲染图表。
- 如需更详细数据（如各区域人口比例、增长率），可参考国家统计局2024年公报。

---
*数据更新至2024年，基于公开统计资料整理。*