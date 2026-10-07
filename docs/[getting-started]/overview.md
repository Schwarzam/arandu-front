# About Arandu

Arandu is a specialised alert broker for NASA's Nancy Grace Roman Space Telescope. It turns alerts from the Roman mission into data that astronomers can search, inspect, and use for science.

The name **Arandu** means *wisdom* in Guarani, one of Brazil's native languages.

## What Arandu does

Arandu receives the alert stream produced by the Roman Alerts Promptly from Image Differencing (**RAPID**) Project Infrastructure Team (PIT). Each alert is enriched with scientifically useful information before it becomes available through the portal and programmatic tools.

In practical terms, Arandu helps users:

- explore alerts and their associated astronomical objects;
- inspect multi-band photometry and science, template, and difference-image cutouts;
- find objects by sky position, recent activity, or classification;
- use enriched alerts for follow-up and scientific analysis.

## RAPID and Roman alerts

RAPID is the image-difference pipeline being developed at IPAC/Caltech. Image differencing compares a new observation with a reference image to identify sources that have changed, producing the alerts that Arandu receives and enriches. The RAPID documentation describes its image-difference pipeline, reference images, pipeline products, and execution architecture.

Learn more in the [official RAPID Image-Difference Pipeline documentation](https://caltech-ipac-rapid.readthedocs.io/en/latest/).

## Project and infrastructure

Arandu is a joint initiative of the Laboratory of Artificial Intelligence for Science at the Brazilian Center for Research in Physics (LAB-AI/CBPF) and the California Institute of Technology (Caltech). It is deployed at CBPF in Rio de Janeiro, Brazil.

The broker is integrated with the AI-SCOPE database. Incoming alerts are processed in memory, where scientific enrichment—including real-versus-artifact classification, catalogue crossmatches, and related analysis—can be applied before results are stored. The alert stream is available in real time through Kafka.

Arandu and AI-SCOPE catalogues can also be accessed through an API using the Python `adss` package. A dedicated Arandu package is in development.

## Goals

- Enrich alerts with science filters and classifications.
- Enable rapid crossmatching with existing catalogues.
- Provide an approachable query interface for filtering data.
- Support community-developed enrichment filters.
- Offer a web portal for exploring and visualising alerts.

## Team and contact

Arandu is managed by Clécio de Bom, Ashish Mahabal, Gabriel Teixeira, and Gustavo Schwarz.

For questions, collaboration proposals, or feedback, contact the team at [arandu@cbpf.br](mailto:arandu@cbpf.br).
