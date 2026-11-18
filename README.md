# Genie Agents Deployment Checklist

An interactive checklist for taking Databricks Genie Agents from a validated proof of concept to an enterprise rollout,
published with GitHub Pages: **https://koritadenada.github.io/genie-deployment-checklist/**

- `index.html`: the checklist. It follows the Genie Agents Enterprise Deployment Guide (Fast Start, Deployment Lifecycle,
  Technical Onboarding Checklist and the six Success Pillars) and adds Genie One, Genie Ontology, Domains, Pages,
  certification, bundles and MCP. Progress and milestone owners are saved in the browser.
- `genie-deployment-guide.html`: the full deployment guide, downloadable from the checklist's
  **Get Genie Deployment document** button.
- CI/CD for Genie Agents lives in its own repository, ready to copy: [koritadenada/genie-agents-ci-cd](https://github.com/koritadenada/genie-agents-ci-cd)
  (dev, staging and prod, deployed benchmarks, and a benchmark gate that only promotes to prod above 80% accuracy).