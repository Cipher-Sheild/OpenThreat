# Third party resources

The root MIT license covers original project code and documentation. It does not replace upstream licenses for dependencies, reference data, model weights, training corpora, or third-party text visible in application screenshots.

## MITRE ATT&CK

`nlp-service/app/resources/attack_groups.json`, `attack_software.json`, and `attack_techniques.json` are transformed extracts of MITRE ATT&CK Enterprise STIX data. Names and aliases were selected into compact dictionaries; technique descriptions were shortened. The original terms and copyright designation are retained in [licenses/MITRE-ATTACK.txt](licenses/MITRE-ATTACK.txt). Source: https://github.com/mitre/cti. Terms: https://attack.mitre.org/resources/terms-of-use/. Inclusion does not imply endorsement.

## TRAM

`nlp-service/app/resources/tram_examples.json` contains retrieval anchors transformed from the TRAM `data/tram2-data/single_label.json` resource. Examples were selected and reshaped into text, document and technique fields. The source is https://github.com/center-for-threat-informed-defense/tram. Apache 2.0 terms and the original notice are retained in [licenses/TRAM-APACHE-2.0.txt](licenses/TRAM-APACHE-2.0.txt) and [licenses/TRAM-NOTICE.txt](licenses/TRAM-NOTICE.txt). Source report excerpts retain their applicable rights.

## External models and corpora

SecureBERT, BGE, CyberNER, AZERG and CTI-HAL retain their upstream terms. Training corpora, trained checkpoints and report collections are not redistributed in this repository. Consult [models and data](docs/models-and-data.md) before downloading or distributing them. Package-specific licenses are supplied by their upstream distributions.

## Screenshots

Images document the application interface. Visible source titles, publisher names and short evidence excerpts belong to their respective sources. Screenshots are operational snapshots rather than an independently annotated benchmark.
