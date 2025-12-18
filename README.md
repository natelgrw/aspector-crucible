# ASPECTOR Foundry: Programmatic Op-Amp Netlist Generation

ASPECTOR Foundry is a tool for generating diverse op-amp Spectre netlists for dataset creation and design space exploration using a graph-based random generation approach. It synthesizes valid circuit topologies and exports them as Cadence Spectre compatible `.scs` files.

ASPECTOR Foundry is part of the ASPECTOR suite, a collection of tools for AI-driven op-amp design and analysis. It is designed to be used in tandem with ASPECTOR Core, a Spectre netlist simulation pipeline for performance optimization and data collection.

Current Version: **1.1.0**

## 💎 Features

- Generates unique op-amp topologies by randomly connecting components while adhering to validity rules
- Supports both single ended and differential op-amp architectures
- Automatically identifies and pairs transistors based on shared gates and symmetric connections
- Generates netlists with parameterized device sizes (`nA`, `nB`) and passive values (`nR`, `nC`) for easy optimization or sweeping


## 📖 How to Use

Ensure you have a Python environment with the necessary dependencies. You can create a Conda environment using the provided YAML file:

```bash
conda env create -f aspfoundry.yml
conda activate aspfoundry
```

Examples of netlist generation can be found in `foundry_demo.ipynb`.

Generated netlists are saved in the `results/` directory as `.scs` files.

The netlists include core circuit topology, parameter definitions for device sizes, 
testbench setup for ASPECTOR Core analysis, and conditional model inclusions based 
on total FET count.
