import itertools
import networkx as nx
import os
import sys
import random
from components import Component, Transistor, Resistor, Capacitor
from templates import SINGLE_ENDED_TEMPLATE, DIFFERENTIAL_TEMPLATE

RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

class NetlistGenerator:
    def __init__(self, num_nfet, num_pfet, num_res, num_cap, mode):
        self.num_nfet = num_nfet
        self.num_pfet = num_pfet
        self.num_res = num_res
        self.num_cap = num_cap
        self.mode = mode # 'single_ended' or 'differential'
        
        self.components = []
        self._init_components()
        
        # Define available fixed nets
        self.fixed_nets = ['vdd!', 'gnd!']
        if mode == 'single_ended':
            self.io_nets = ['Vinp', 'Vinn', 'Voutp']
        else:
            self.io_nets = ['Vinp', 'Vinn', 'Voutp', 'Voutn']
            
        # Bias nets pool (can be expanded)
        self.bias_nets = ['Vbiasn0', 'Vbiasn1', 'Vbiasn2', 'Vbiasp0', 'Vbiasp1', 'Vbiasp2']

    def _init_components(self):
        idx = 0
        for i in range(self.num_nfet):
            self.components.append(Transistor(f"MM{idx}", 'nfet'))
            idx += 1
        for i in range(self.num_pfet):
            self.components.append(Transistor(f"MM{idx}", 'pfet'))
            idx += 1
        for i in range(self.num_res):
            self.components.append(Resistor(f"R{i}"))
        for i in range(self.num_cap):
            self.components.append(Capacitor(f"C{i}"))

    def generate_random(self, max_netlists=500, max_attempts=100000):
        """
        Generates valid topologies using random sampling.
        """
        # Gather terminals that need assignment
        # First, fix bodies
        for comp in self.components:
            if isinstance(comp, Transistor):
                if comp.type == 'nfet':
                    comp.connect('B', 'gnd!')
                else:
                    comp.connect('B', 'vdd!')

        self.terminals_to_assign = []
        for comp in self.components:
            terms = []
            if isinstance(comp, Transistor):
                terms = ['D', 'G', 'S']
            else:
                terms = comp.terminals
            
            for t in terms:
                self.terminals_to_assign.append((comp, t))
        
        # Define the pool of available nets
        # Fixed + IO + Bias + Internal
        # Heuristic: Max internal nets = Num Components
        self.internal_nets = [f"net{i}" for i in range(len(self.components) + 2)]
        self.available_nets = self.fixed_nets + self.io_nets + self.bias_nets + self.internal_nets
        
        self.generated_count = 0
        attempts = 0
        
        while self.generated_count < max_netlists and attempts < max_attempts:
            attempts += 1
            
            # Randomly assign all terminals
            for comp, term in self.terminals_to_assign:
                # Heuristic: Bias towards internal nets to encourage connectivity?
                # For now, uniform random.
                net = random.choice(self.available_nets)
                comp.connect(term, net)
                
            if self._is_valid():
                self.generated_count += 1
                self.write_netlist(self.generated_count)
                if self.generated_count % 10 == 0:
                    print(f"Generated {self.generated_count}/{max_netlists} (Attempts: {attempts})")

    def _is_valid(self):
        # 1. Check for floating nets (nets with < 2 connections, unless it's an IO/Power/Bias)
        net_counts = {n: 0 for n in self.available_nets}
        for comp in self.components:
            for t in comp.terminals:
                n = comp.get_net(t)
                if n: net_counts[n] += 1
        
        # Check internal nets usage
        for net in self.internal_nets:
            if net_counts[net] == 1: # Floating end
                return False
            # If 0, it's just unused, which is fine (but maybe wasteful)
        
        # 2. Check for trivial component connections
        for comp in self.components:
            if isinstance(comp, Transistor):
                d = comp.get_net('D')
                s = comp.get_net('S')
                if d == s: return False # Shorted channel
                
                # Check if all terminals are VDD/GND
                is_all_rails = True
                for t in comp.terminals:
                    n = comp.get_net(t)
                    if n not in self.fixed_nets:
                        is_all_rails = False
                        break
                if is_all_rails: return False

        # 3. Check Path from Input to Output
        # Build graph
        G = nx.Graph()
        for comp in self.components:
            nets = [comp.get_net(t) for t in comp.terminals if comp.get_net(t)]
            for i in range(len(nets)):
                for j in range(i+1, len(nets)):
                    G.add_edge(nets[i], nets[j])
        
        # Check connectivity
        # Ensure IO nets are in the graph
        if 'Vinp' not in G or 'Voutp' not in G: return False
        
        # For single ended: Vinp -> Voutp
        if self.mode == 'single_ended':
            if not nx.has_path(G, 'Vinp', 'Voutp'): return False
        else:
             if 'Vinn' not in G or 'Voutn' not in G: return False
             if not (nx.has_path(G, 'Vinp', 'Voutp') or nx.has_path(G, 'Vinp', 'Voutn')): return False
             
        return True

    def identify_pairs(self):
        """
        Assigns nA_i, nB_i parameters based on pairing rules.
        Rules:
        1. Same Gate & Same Type.
        2. Symmetric connection to Voutp/Voutn.
        3. Recursive symmetry.
        """
        comps = [c for c in self.components if isinstance(c, Transistor)]
        pairs = [] # List of sets
        processed = set()
        
        # Helper to check if two nets are "symmetric"
        # For now, symmetric means one is Voutp and other is Voutn (or vice versa)
        # OR they are connected to a known pair in a symmetric way.
        # This is recursive. 
        
        # Let's start with Rule 1 (Same Gate) as a baseline
        # and Rule 2 (Voutp/Voutn) as seeds.
        
        # We will build a "symmetry map" of nets.
        # Initially {Voutp: Voutn, Voutn: Voutp, Vinp: Vinn, Vinn: Vinp} (if diff)
        sym_nets = {}
        # Always treat inputs as symmetric for pairing purposes (differential pair detection)
        sym_nets['Vinp'] = 'Vinn'
        sym_nets['Vinn'] = 'Vinp'
        
        if self.mode == 'differential':
            sym_nets['Voutp'] = 'Voutn'
            sym_nets['Voutn'] = 'Voutp'
            
        # Iterative pairing
        changed = True
        while changed:
            changed = False
            
            for i in range(len(comps)):
                if comps[i] in processed: continue
                c1 = comps[i]
                
                for j in range(i+1, len(comps)):
                    if comps[j] in processed: continue
                    c2 = comps[j]
                    
                    if c1.type != c2.type: continue
                    
                    is_pair = False
                    
                    # Rule 1: Same Gate AND (Same Source OR Symmetric Source)
                    # This prevents pairing a tail source with a cascode just because they share a bias gate.
                    if c1.get_net('G') == c2.get_net('G'):
                        s1 = c1.get_net('S')
                        s2 = c2.get_net('S')
                        if s1 == s2:
                            is_pair = True
                        elif s1 in sym_nets and sym_nets[s1] == s2:
                            is_pair = True
                        
                    # Rule 2 & 3: Symmetric connections
                    # Check if D, G, S are symmetric
                    # If G1 is sym to G2, D1 sym to D2, S1 sym to S2 -> Pair
                    # (If connected to same net, it's self-symmetric)
                    
                    match_count = 0
                    for term in ['D', 'G', 'S']:
                        n1 = c1.get_net(term)
                        n2 = c2.get_net(term)
                        
                        if n1 == n2: # Connected to same net
                            match_count += 1
                        elif n1 in sym_nets and sym_nets[n1] == n2: # Symmetric nets
                            match_count += 1
                            
                    if match_count == 3:
                        is_pair = True
                        
                    if is_pair:
                        pairs.append({c1, c2})
                        processed.add(c1)
                        processed.add(c2)
                        changed = True
                        
                        # Update sym_nets based on this new pair
                        # If c1.D is netA and c2.D is netB, then netA and netB are symmetric
                        for term in ['D', 'G', 'S']:
                            n1 = c1.get_net(term)
                            n2 = c2.get_net(term)
                            if n1 != n2:
                                sym_nets[n1] = n2
                                sym_nets[n2] = n1
                        break
        
        # Remaining singletons
        for c in comps:
            if c not in processed:
                pairs.append({c})
                
        # Assign parameters
        param_map = {}
        param_idx = 1
        # Sort pairs for deterministic output
        sorted_pairs = sorted(pairs, key=lambda x: min(c.name for c in x))
        
        for group in sorted_pairs:
            nA = f"nA{param_idx}"
            nB = f"nB{param_idx}"
            for c in group:
                param_map[c] = (nA, nB)
            param_idx += 1
            
        return param_map

    def write_netlist(self, index):
        filename = f"{self.mode}{index}.scs"
        filepath = os.path.join(RESULTS_DIR, filename)
        
        param_map = self.identify_pairs()
        
        # Build component string
        comp_lines = []
        
        # Header comment
        comp_lines.append(f"*---Generated Circuit {index}---")
        
        # Transistors
        # Format: MM{i} {D} {G} {S} {B} {type} l={nA} nfin={nB}
        # Note: In example, order is D G S B? 
        # Example: MM12 net12 Vbiasp2 net37 vdd! pfet l=nA6 nfin=nB6
        # Spectre syntax: Name D G S B Model ...
        
        for comp in self.components:
            if isinstance(comp, Transistor):
                d = comp.get_net('D')
                g = comp.get_net('G')
                s = comp.get_net('S')
                b = comp.get_net('B')
                nA, nB = param_map[comp]
                comp_lines.append(f"{comp.name} {d} {g} {s} {b} {comp.type} l={nA} nfin={nB}")
            elif isinstance(comp, Resistor):
                p = comp.get_net('P')
                n = comp.get_net('N')
                # Extract index from name R{i}
                idx = comp.name[1:]
                param_name = f"nR{idx}"
                comp_lines.append(f"{comp.name} ({p} {n}) resistor r={param_name}")
            elif isinstance(comp, Capacitor):
                p = comp.get_net('P')
                n = comp.get_net('N')
                idx = comp.name[1:]
                param_name = f"nC{idx}"
                comp_lines.append(f"{comp.name} ({p} {n}) capacitor c={param_name}")
                
        core_netlist = "\n".join(comp_lines)
        
        
        # Create parameter string for the .scs file
        # e.g. parameters nA1=1u nB1=1 ...
        # The example used {{nA1}}, implying it might be a template output. 
        # But "Write ... as separate Spectre .scs netlists" implies valid simulation files.
        # I will give them default values to make them valid.
        
        # We need to list all nA_i, nB_i used
        used_params = set()
        for p in param_map.values():
            used_params.add(p[0])
            used_params.add(p[1])
            
        # Add passive params
        for comp in self.components:
            if isinstance(comp, Resistor):
                idx = comp.name[1:]
                used_params.add(f"nR{idx}")
            elif isinstance(comp, Capacitor):
                idx = comp.name[1:]
                used_params.add(f"nC{idx}")

        param_list = []
        for p in sorted(used_params):
            if p.startswith('nA'):
                param_list.append(f"{p}=1u")
            else:
                param_list.append(f"{p}=1")
        
        extra_params = " ".join(param_list)
        
        # Calculate fet_num
        fet_num = self.num_nfet + self.num_pfet
        
        # Select Template
        if self.mode == 'single_ended':
            template = SINGLE_ENDED_TEMPLATE
        else:
            template = DIFFERENTIAL_TEMPLATE
            
        # Fill Template
        # We'll do simple string replacement for the placeholders I defined
        # Note: The original file had {{...}}. I will replace those with values or keep them if they are for post-processing.
        # Given the user request, I should probably produce a file that IS a template like the input?
        # "single_ended opamp netlists need to be in the format of single_ended1.scs"
        # The input file HAS {{nA1}}. 
        # So I should probably preserve that format?
        # "Write all those combinations ... as separate Spectre .scs netlists"
        # If I write {{nA1}}, spectre won't run unless it's preprocessed.
        # But maybe that's what they want.
        # Let's look at the user prompt again: "single_ended opamp netlists need to be in the format of single_ended1.scs"
        # I will output exactly that format, including {{...}}.
        
        # Re-generating the param string to match format: nA1={{nA1}}
        param_list_tpl = []
        for p in sorted(used_params):
            param_list_tpl.append(f"{p}={{{{{p}}}}}")
        extra_params_tpl = " ".join(param_list_tpl)
        
        content = template.replace("<<FET_NUM>>", "{{fet_num}}")
        content = content.replace("<<EXTRA_PARAMS>>", extra_params_tpl)
        content = content.replace("<<CORE_NETLIST>>", core_netlist)
        
        # Also need to handle the "include" logic which was jinja-like in the source.
        # I will just evaluate it here and write the correct include line.
        # The example had: {% if fet_num == 7 %} ...
        # I will replace that block with the actual include.
        
        include_lines = """{% if fet_num == 7 %}
include "/homes/natelgrw/Documents/titan_foundation_model/lstp/7nfet.pm"
include "/homes/natelgrw/Documents/titan_foundation_model/lstp/7pfet.pm"
{% elif fet_num == 10 %}
include "/homes/natelgrw/Documents/titan_foundation_model/lstp/10nfet.pm"
include "/homes/natelgrw/Documents/titan_foundation_model/lstp/10pfet.pm"
{% elif fet_num == 14 %}
include "/homes/natelgrw/Documents/titan_foundation_model/lstp/14nfet.pm"
include "/homes/natelgrw/Documents/titan_foundation_model/lstp/14pfet.pm"
{% elif fet_num == 16 %}
include "/homes/natelgrw/Documents/titan_foundation_model/lstp/16nfet.pm"
include "/homes/natelgrw/Documents/titan_foundation_model/lstp/16pfet.pm"
{% elif fet_num == 20 %}
include "/homes/natelgrw/Documents/titan_foundation_model/lstp/20nfet.pm"
include "/homes/natelgrw/Documents/titan_foundation_model/lstp/20pfet.pm"
{% endif %}"""

        content = content.replace("<<INCLUDES>>", include_lines)

        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Written {filepath}")
