const TEAM = {
  aq: 72,
  delta: 4,
  history: [
    { label: 'jun', value: 67 },
    { label: 'jul', value: 68 },
    { label: 'ago', value: 72 }
  ],
  tokens: '48.2M',
  cost: '$310',
  costDelta: -8,
  pillars: [
    { name: 'Breadth', weight: '30%', value: 64 },
    { name: 'Craft', weight: '30%', value: 78 },
    { name: 'Efficiency', weight: '25%', value: 70 },
    { name: 'Savvy', weight: '15%', value: 81 }
  ],
  models: [
    { label: 'Sonnet 4.5', value: 46 },
    { label: 'Opus 4.1', value: 31 },
    { label: 'GPT-5', value: 15 },
    { label: 'Otros', value: 8 }
  ],
  tiers: [
    { name: 'Architect', range: '80+', count: 1 },
    { name: 'Operator', range: '65–79', count: 3 },
    { name: 'Pilot', range: '<65', count: 2 }
  ],
  uploaded: 5
};

const PILLAR_META = {
  Breadth: { max: 30, axes: ['Tool range', 'Skill use', 'MCP reach'] },
  Craft: { max: 35, axes: ['Verification', 'Error recovery', 'Iteration'] },
  Efficiency: { max: 20, axes: ['Actions/prompt', 'Fanout', 'Planning'] },
  Savvy: { max: 15, axes: ['Compounding', 'Judgment'] }
};

const PEOPLE = [
  {
    id: 'ana', name: 'Ana P.', email: 'ana@empresa.com', aq: 84, delta: 6,
    tier: 'Architect', top: 'Craft', upload: 'hace 2 días',
    quote: 'Blueprint, then bulldozer — planificá amplio, ejecutá angosto',
    pillars: { Breadth: 71, Craft: 92, Efficiency: 80, Savvy: 85 },
    scorecard: { execution: 9.1, planning: 9.8, engineering: 8.6 },
    suggestions: [
      'Craft 92: podés mentorear Breadth al resto — solo vos y Bruno orquestan subagentes.',
      'Efficiency: 3 sesiones de más de 2h sin checkpoint la semana pasada.'
    ]
  },
  {
    id: 'bruno', name: 'Bruno M.', email: 'bruno@empresa.com', aq: 75, delta: 2,
    tier: 'Operator', top: 'Savvy', upload: 'hace 5 días',
    quote: 'Explorador — probá rápido, decidí después',
    pillars: { Breadth: 66, Craft: 74, Efficiency: 72, Savvy: 88 },
    scorecard: { execution: 8.4, planning: 7.9, engineering: 8.1 },
    suggestions: [
      'Savvy 88 es tu fuerte; Breadth 66 sube rápido con fan-out de subagentes en tareas repetitivas.',
      'Craft: revisá diffs antes de aceptar — 30% de accepts sin lectura.'
    ]
  },
  {
    id: 'carla', name: 'Carla S.', email: 'carla@empresa.com', aq: 71, delta: -3,
    tier: 'Operator', top: 'Efficiency', upload: 'hace 1 semana',
    quote: 'Sprinter — sesiones largas, foco profundo',
    pillars: { Breadth: 60, Craft: 76, Efficiency: 79, Savvy: 70 },
    scorecard: { execution: 8.8, planning: 6.9, engineering: 7.6 },
    suggestions: [
      'Trend −3: el mes tuvo sesiones largas sin checkpoints — cortá en hitos chicos.',
      'Breadth 60: probá delegar tests a un subagente.'
    ]
  },
  {
    id: 'elena', name: 'Elena V.', email: 'elena@empresa.com', aq: 69, delta: 1,
    tier: 'Operator', top: 'Craft', upload: 'hace 3 días',
    quote: 'Metódica — un paso verificado a la vez',
    pillars: { Breadth: 58, Craft: 80, Efficiency: 68, Savvy: 72 },
    scorecard: { execution: 7.4, planning: 8.6, engineering: 8.9 },
    suggestions: [
      'Breadth 58 es tu pilar más flojo: empezá con 1 subagente para migraciones.',
      'Efficiency: agrupá prompts chicos en uno con contexto.'
    ]
  },
  {
    id: 'fede', name: 'Fede L.', email: 'fede@empresa.com', aq: 62, delta: 0,
    tier: 'Pilot', top: 'Savvy', upload: 'hace 4 días',
    quote: 'Aprendiz veloz — copiá lo que funciona',
    pillars: { Breadth: 55, Craft: 62, Efficiency: 61, Savvy: 74 },
    scorecard: { execution: 6.8, planning: 6.2, engineering: 6.5 },
    suggestions: [
      'Pilot → Operator: te faltan 3 puntos; el camino corto es Craft (revisión de diffs).',
      'Savvy 74 ya es sólido para tu antigüedad con agentes.'
    ]
  },
  {
    id: 'diego', name: 'Diego R.', email: 'diego@empresa.com', aq: 58, delta: null,
    tier: 'Pilot', top: 'Breadth', upload: 'junio',
    quote: 'Sin datos frescos — perfil de junio',
    pillars: { Breadth: 52, Craft: 60, Efficiency: 58, Savvy: 63 },
    scorecard: { execution: 6.1, planning: 5.8, engineering: 6.4 },
    suggestions: [
      'Sin datos de agosto: corré gnomon push para tener sugerencias frescas.',
      'Con datos de junio: Breadth 52 era el punto de partida sugerido.'
    ]
  }
];

const COUNTERS = [
  { k: 'planning ratio', v: '82%' },
  { k: 'error recovery', v: '98%' },
  { k: 'error rate', v: '2.6' },
  { k: 'iter depth', v: '2.3×' },
  { k: 'git churn', v: '8.2M' },
  { k: 'fanout mediana', v: '3.5' },
  { k: 'compounding writes', v: '91' },
  { k: 'días activos', v: '14' }
];

const PERSON_MODELS = [
  { label: 'Opus 4.8', value: 60 },
  { label: 'Fable 5', value: 28 },
  { label: 'Haiku 4.5', value: 12 }
];

const MONTHS = ['Agosto 2026', 'Julio 2026', 'Junio 2026'];
