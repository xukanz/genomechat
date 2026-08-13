import type { LandingCopy } from './copy.types'

export const zh: LandingCopy = {
  nav: {
    architecture: '架构',
    data: '数据',
    useCases: '用例',
    security: '安全',
    openApp: '进入应用',
    getStarted: '开始使用',
    menu: '打开菜单',
    language: '切换语言',
  },
  hero: {
    eyebrow: 'AI 驱动的科研平台',
    titleLead: '认识一下',
    subtitle: '每一次突破都始于一个问题。GenomeChat 拆掉好奇与发现之间的那堵墙。',
    cta: '立即体验',
    stats: {
      records: '可查询数据行',
      agents: '协作智能体',
      databases: '数据库类型',
      sources: '公共数据源',
    },
  },
  badges: {
    k8s: '容器原生，可上 Kubernetes',
    sse: 'SSE 实时流式响应',
  },
  impact: {
    eyebrow: '为什么这件事重要',
    title: '让基因组学发现来得更快',
    body: '科研中省下的每一分钟，都让患者离更好的治疗更近一步。GenomeChat 帮研究者把从提问到发现的路径缩短——原本几天的分析，现在几分钟完成。',
  },
  architecture: {
    eyebrow: '架构',
    title: '多智能体协作架构',
    subtitle: '五个各司其职的智能体协同处理复杂科研问题，任务由编排者智能分发',
    agents: {
      coordinator: { title: '协调者', description: '路由提问' },
      sqlAgent: { title: 'SQL 智能体', description: '查询数据' },
      coder: { title: '编码者', description: '执行代码' },
      researcher: { title: '文献智能体', description: '检索文献' },
    },
    flow: {
      query: '提问',
      coordinator: '协调者',
      orchestrator: '编排者',
      workers: '工作节点',
    },
  },
  dataScale: {
    eyebrow: '数据规模',
    title: '每个数字都可核对',
    subtitle: '三个公共基因组学数据源，本地构建，随时切换',
    chartTitle: '各表行数',
    rowsUnit: '行',
    footnote:
      'ClinVar 随 variant_summary 周更 · GWAS Catalog 采用 CC BY 4.0 · Ensembl 固定在 release-116 · 全部由 build_genomics_databases.py 本地构建，可复现',
    tables: {
      clinvar: 'ClinVar 变异断言',
      gwasAssociations: 'GWAS 关联',
      gwasStudies: 'GWAS 研究',
      ensemblGenes: 'Ensembl 基因',
      ensemblExons: 'Ensembl 外显子',
      ensemblTranscripts: 'Ensembl 转录本',
    },
  },
  comparison: {
    eyebrow: '效率对比',
    title: '重塑你的科研流程',
    subtitle: '看看 GenomeChat 如何改变研究者探索数据的方式',
    traditionalTab: '传统方式',
    cta: '亲自感受差异',
    rows: [
      { traditional: '手写 SQL，反复调试数天', platform: '自然语言提问，几分钟出结果' },
      { traditional: '需要 SQL / Python 功底', platform: '不写一行代码' },
      { traditional: '静态报表与导出文件', platform: '实时流式响应' },
      { traditional: '一次只能连一个库', platform: '三个基因组学数据源，运行时切换' },
      { traditional: '人工翻文献做验证', platform: '内置文献交叉验证' },
      { traditional: '本地 notebook，状态留不住', platform: '容器化部署，会话状态持久' },
    ],
  },
  databases: {
    eyebrow: '数据基础设施',
    title: '多数据库架构',
    subtitle: '支持 7 种数据库，运行时切换，无需重启',
    items: {
      sqlite: 'ClinVar 变异档案',
      duckdb: 'GWAS / Ensembl Parquet 分析',
      mysql: '企业级 SQL',
      postgres: '企业级 SQL',
      mssql: 'Microsoft SQL Server',
      athena: 'AWS 无服务器 SQL',
      mongodb: '检查点与元数据',
    },
  },
  useCases: {
    eyebrow: '应用场景',
    title: '科研用例',
    subtitle: '从探索性研究到临床数据分析——全部通过自然语言完成',
    exampleLabel: '示例提问',
    items: {
      variants: {
        title: '变异解读',
        description: '查询 448 万条 ClinVar 变异—疾病断言',
        details: [
          '按临床意义与 ACMG 评审等级筛选变异',
          '按基因拆解致病与可能致病的判定分布',
          '量化基因 panel 中意义未明变异（VUS）的占比',
          '绘制致病变异在各染色体上的分布密度',
        ],
        example: 'BRCA1 上报告了多少致病和可能致病的变异？按变异类型拆开看',
      },
      gwas: {
        title: '性状遗传学',
        description: '探索 119 万条经过策展的 SNP—性状关联',
        details: [
          '找出任意性状的全基因组显著位点（p < 5e-8）',
          '按关联性状数量排出多效性最强的 SNP',
          '把效应量与风险等位基因频率放在一起看',
          '关联研究元数据，补上样本量与祖源背景',
        ],
        example: '找出 2 型糖尿病的全基因组显著关联，列出最强的 25 条及其映射基因',
      },
      literature: {
        title: '文献验证',
        description: '把计算结果与已发表研究相互印证',
        details: [
          '通过 Europe PMC 检索生物医学文献',
          '按 DOI 精确取回文献用于引用',
          '用已发表结论校验计算得到的发现',
          '生成带出处标注的文献综述',
        ],
        example: '找一批关于冠心病多基因风险评分的近期论文',
      },
      annotation: {
        title: '基因注释',
        description: '查询 GRCh38 的基因、转录本与外显子注释',
        details: [
          '按基因符号或 Ensembl ID 定位基因、转录本与外显子',
          '读取 GRCh38 上的染色体、起止坐标与链方向',
          '筛选 MANE Select 转录本作为每个基因的代表',
          '为 ClinVar 与 GWAS 的结果锚定参考基因模型',
        ],
        example: '列出 TP53 所有蛋白编码转录本，附上各自的外显子数与基因组坐标',
      },
    },
  },
  security: {
    eyebrow: '合规与安全',
    title: '面向生产的安全设计',
    subtitle: '从认证、沙箱到 SQL 校验，每一层都为可信结果服务',
    items: {
      auth: { title: 'JWT 认证', description: '基于令牌的认证，支持自动刷新，密码经 bcrypt 哈希' },
      sandbox: {
        title: '隔离沙箱',
        description: '代码在独立容器中执行：非 root、只读根文件系统、PID 与资源配额',
      },
      grounding: {
        title: 'Schema 锚定',
        description: '智能体只能看到真实的库表结构，从源头压制幻觉',
      },
      kubernetes: {
        title: 'Kubernetes 就绪',
        description: '容器化部署，密钥经 Vault 注入，前端 API 地址运行时下发',
      },
      validation: {
        title: '多层校验',
        description: 'SQL 执行前经 LLM 复核、拒绝 DDL、自动追加行数上限',
      },
      isolation: {
        title: '用户隔离',
        description: 'MongoDB 检查点以 用户ID:会话ID 为键，会话状态互不可见',
      },
    },
    badges: {
      auth: 'JWT 认证',
      sandboxed: '沙箱隔离',
      validated: 'SQL 校验',
      deployable: '容器化部署',
    },
  },
  cta: {
    eyebrow: '开始使用',
    title: '准备好改变基因组学研究了吗？',
    subtitle: '查询变异与关联记录、生成可视化、验证结论——全部通过一场对话完成',
    button: '立即体验',
  },
}
