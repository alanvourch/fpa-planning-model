// Ready-to-paste entry for Portfolio/js/projects.js (same shape as the existing
// entries). Suggested position: directly after 'fpa-agent-team', so the close
// project and the planning project sit together under FINANCE & FP&A.
// Thumbnails: export two screenshots of site/index.html (the hero and the
// scenario charts) as images/projects/fpa-planning-hero.webp and
// images/projects/fpa-planning-scenarios.webp before enabling this entry.
  {
    id: 'fpa-planning-model',
    category: 'finance',
    featured: true,
    title: 'Driver-Based Planning: Headcount, Cloud and Runway for a SaaS Scale-Up',
    shortDesc: 'An 18-month driver-based plan for a Series C software company that decides how much to hire, where, and what to commit on cloud, under base, upside and downside scenarios, with two guardrails and a recommendation the tests can check.',
    fullDesc: 'Northlight is a fictional USD 24M ARR software company with people in Montreal, Paris and Austin. The model builds its plan from drivers rather than typed growth rates: every seat is costed by role and location (salary, employer taxes from published 2026 rate tables, benefits, ramp, merit), new customers come from ramped sales capacity, cloud cost comes from compute units per customer, and cash follows the P&L through receivables and deferred revenue. Three hiring plans crossed with two cloud purchasing choices are run under three scenarios; two guardrails (18 months of downside runway, a 74% gross margin floor) decide, and the model recommends the phased plan with a one-year cloud commitment. It also produces a monthly actual-versus-budget bridge that ties to the cent, a versioned assumption log, an Excel workbook whose subtotals are live formulas, a one-page CFO memo and a five-slide board pack. No language model anywhere: the finance machinery is the point.',
    highlights: [
      'Recommendation generated from the model: phased hiring plus a cloud commitment; the front-loaded plan fails the downside runway guardrail by about a month',
      'Every hire flows through salary, employer taxes, benefits, ramp and start date to gross margin, opex and cash, and a test checks the exact amount',
      'Actual-versus-budget bridge splits every line into volume, price, headcount, rate and usage; components sum to the EBITDA variance to the cent',
      'Assumptions carry a source label (benchmark, derived or judgment) and a change log; snapshot plus log reproduces the current file',
      'Excel export with live formulas, recalculated by Excel itself in the test suite; every number on the page traces to a model output'
    ],
    skills: ['Driver-Based Planning', 'Scenario Modeling', 'Workforce Planning', 'SaaS Metrics', 'Cash Runway', 'Python', 'Excel'],
    thumb: 'images/projects/fpa-planning-hero.webp',
    hover: 'images/projects/fpa-planning-scenarios.webp',
    link: 'https://alanvourch.com/fpa-planning-model/',
    linkLabel: 'Open the Live Case Study'
  },
