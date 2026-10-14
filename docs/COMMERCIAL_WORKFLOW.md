# Stage-1 Commercial Workflow

## Goal

Get Nexora to the first paying HVAC customers as quickly as possible while measuring value honestly.

## Customer promise

Nexora helps an HVAC business respond to leads, qualify them, follow up, book appointments, and recover opportunities the business might otherwise lose.

## Core loop

```text
lead arrives
  -> qualification
  -> appointment proposal
  -> follow-up when necessary
  -> booking
  -> completed job
  -> actual revenue
  -> ROI evidence
```

## Commercial metrics

Nexora must keep these separate:

- **Pipeline** — estimated value of open work.
- **Booked pipeline** — estimated value attached to confirmed appointments.
- **Completed revenue** — actual or confirmed job value entered after completion.
- **Recovered revenue** — booked value where Nexora Follow-Up participated before conversion.
- **Open opportunity** — value of active, unbooked leads that still need work.

## Opportunity engine

The first opportunity engine is intentionally deterministic. It ranks active unbooked leads by estimated value and recommends the next action using stage and contact recency.

Later versions can add conversion probability, service-area fit, capacity, customer history, seasonality, and model-assisted ranking.

## Revenue rule

Never present estimated pipeline as money already generated. Customer-facing ROI must clearly distinguish estimates from completed revenue.
