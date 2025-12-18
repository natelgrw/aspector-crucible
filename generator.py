import itertools
import networkx as nx
import os
import sys
import random
from components import Component, Transistor, Resistor, Capacitor
from templates import SINGLE_ENDED_TEMPLATE, DIFFERENTIAL_TEMPLATE

RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

class Subcircuit:
    def __init__(self, name, num_nfet, num_pfet, num_res, num_cap, mode, 
                 n_vbiasn=3, n_vbiasp=3, n_ibias=1, n_internal_nets=5, is_main=False, 
                 assigned_ports=None):
        # assigned_ports is a dict: {net_name: 'I' or 'O'}
        self.name = name
        self.num_nfet = num_nfet
        self.num_pfet = num_pfet
        self.num_res = num_res
        self.num_cap = num_cap
        # single ended or differential
        self.mode = mode
        self.is_main = is_main
        self.assigned_ports = assigned_ports if assigned_ports else {}
        
        self.components = []
        self._init_components()
        
        # fixed nets
        self.fixed_nets = ['vdd!', 'gnd!']
        
        # IO nets - only belonging to first main subcircuit
        if self.is_main:
            if mode == 'single_ended':
                self.all_io_nets = ['Vinp', 'Vinn', 'Voutp']
            else:
                self.all_io_nets = ['Vinp', 'Vinn', 'Voutp', 'Voutn']
        else:
            self.all_io_nets = []
            
        # bias nets
        self.bias_nets = [f'Vbiasn{i}' for i in range(n_vbiasn)] + \
                          [f'Vbiasp{i}' for i in range(n_vbiasp)] + \
                          [f'Ibias{i}' for i in range(n_ibias)]
        
        # internal nets
        self.internal_nets = [f"net{i}" for i in range(n_internal_nets)]
        
        # Ensure assigned ports are in the pool
        for net in self.assigned_ports:
            if net not in self.all_io_nets and net not in self.bias_nets:
                # If it's not a standard IO/Bias, it must be something special or internal net elevation
                pass

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

    def generate_structure(self, max_attempts=1000):
        """
        Generates a valid topology for this subcircuit.
        Returns True if successful, False otherwise.
        """
        # gather terminals
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
        
        # pool of available nets: ONLY use planned ports, fixed rails, and internal nets
        self.available_nets = self.fixed_nets + list(self.assigned_ports.keys()) + self.internal_nets
        
        for _ in range(max_attempts):
            import random
            # First, ensure every assigned port is used by at least one random terminal
            # to fulfill the "Layout matches I/O rules" requirement.
            assigned_nets = sorted(list(self.assigned_ports.keys()))
            remaining_terms = list(self.terminals_to_assign)
            random.shuffle(remaining_terms)
            
            # Map assigned nets to terminals first
            assignments = {}
            if len(assigned_nets) > len(remaining_terms):
                # Too many assigned ports for this small subckt? 
                # This should be caught in planning or just skip this attempt.
                continue
                
            for i, net in enumerate(assigned_nets):
                comp, term = remaining_terms.pop()
                comp.connect(term, net)
                assignments[(comp, term)] = net
                
            # Randomly assign all remaining terminals
            for comp, term in remaining_terms:
                net = random.choice(self.available_nets)
                comp.connect(term, net)
                
            if self._is_valid():
                return True
        
        return False

    def _is_valid(self):
        # floating net check
        net_counts = {n: 0 for n in self.available_nets}
        for comp in self.components:
            for t in comp.terminals:
                n = comp.get_net(t)
                if n: net_counts[n] += 1
        
        # internal net usage
        for net in self.internal_nets:
            if net_counts[net] == 1:
                return False
        
        # trivial connections
        for comp in self.components:
            if isinstance(comp, Transistor):
                d = comp.get_net('D')
                s = comp.get_net('S')
                if d == s: return False
                
                is_all_rails = True
                for t in comp.terminals:
                    n = comp.get_net(t)
                    if n not in self.fixed_nets:
                        is_all_rails = False
                        break
                if is_all_rails: return False
            elif isinstance(comp, (Resistor, Capacitor)):
                p = comp.get_net('P')
                n = comp.get_net('N')
                if p == n: return False

        # check if path exists from input to output
        if self.is_main:
            G = nx.Graph()
            for comp in self.components:
                nets = [comp.get_net(t) for t in comp.terminals if comp.get_net(t)]
                for i in range(len(nets)):
                    for j in range(i+1, len(nets)):
                        G.add_edge(nets[i], nets[j])
            
            if 'Vinp' not in G or 'Voutp' not in G: return False
            
            if self.mode == 'single_ended':
                if not nx.has_path(G, 'Vinp', 'Voutp'): return False
            else:
                 if 'Vinn' not in G or 'Voutn' not in G: return False
                 if not (nx.has_path(G, 'Vinp', 'Voutp') or nx.has_path(G, 'Vinp', 'Voutn')): return False

        # Ensure all assigned ports are actually used (at least one connection)
        # (This is already guaranteed by the construction above, but good to check)
        for net in self.assigned_ports:
            if net_counts.get(net, 0) == 0:
                return False
             
        return True

    def get_pairs(self):
        """
        Returns a list of sets of paired components.
        """
        comps = [c for c in self.components if isinstance(c, Transistor)]
        pairs = []
        processed = set()
        
        sym_nets = {}
        if self.is_main:
            sym_nets['Vinp'] = 'Vinn'
            sym_nets['Vinn'] = 'Vinp'
            
            if self.mode == 'differential':
                sym_nets['Voutp'] = 'Voutn'
                sym_nets['Voutn'] = 'Voutp'
            
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
                    
                    # 1: same gate AND (same source OR symmetric source)
                    if c1.get_net('G') == c2.get_net('G'):
                        s1 = c1.get_net('S')
                        s2 = c2.get_net('S')
                        if s1 == s2:
                            is_pair = True
                        elif s1 in sym_nets and sym_nets[s1] == s2:
                            is_pair = True
                        
                    # 2: symmetric connections
                    match_count = 0
                    for term in ['D', 'G', 'S']:
                        n1 = c1.get_net(term)
                        n2 = c2.get_net(term)
                        
                        if n1 == n2:
                            match_count += 1
                        elif n1 in sym_nets and sym_nets[n1] == n2:
                            match_count += 1
                            
                    if match_count == 3:
                        is_pair = True
                        
                    if is_pair:
                        pairs.append({c1, c2})
                        processed.add(c1)
                        processed.add(c2)
                        changed = True
                        
                        for term in ['D', 'G', 'S']:
                            n1 = c1.get_net(term)
                            n2 = c2.get_net(term)
                            if n1 != n2:
                                sym_nets[n1] = n2
                                sym_nets[n2] = n1
                        break
        
        for c in comps:
            if c not in processed:
                pairs.append({c})
                
        return pairs

    def get_netlist_lines(self, param_map):
        lines = []
        for comp in self.components:
            if isinstance(comp, Transistor):
                d = comp.get_net('D')
                g = comp.get_net('G')
                s = comp.get_net('S')
                b = comp.get_net('B')
                nA, nB = param_map[comp]
                lines.append(f"{comp.name} {d} {g} {s} {b} {comp.type} l={nA} nfin={nB}")
            elif isinstance(comp, Resistor):
                p = comp.get_net('P')
                n = comp.get_net('N')
                idx = comp.name[1:]
                param_name = f"nR{idx}"
                lines.append(f"{comp.name} ({p} {n}) resistor r={param_name}")
            elif isinstance(comp, Capacitor):
                p = comp.get_net('P')
                n = comp.get_net('N')
                idx = comp.name[1:]
                param_name = f"nC{idx}"
                lines.append(f"{comp.name} ({p} {n}) capacitor c={param_name}")
        return lines

class NetlistGenerator:
    def __init__(self, *args):
        self.configs = []
        self.mode = None
        self.n_vbiasn = 0
        self.n_vbiasp = 0
        self.n_ibias = 0
        self.n_internal_nets = 0

        if len(args) < 5:
            raise ValueError("Must provide at least one config, n_vbiasn, n_vbiasp, n_ibias, n_internal_nets, and a mode")
            
        self.mode = args[-1]
        self.n_internal_nets = args[-2]
        self.n_ibias = args[-3]
        self.n_vbiasp = args[-2-2]
        self.n_vbiasn = args[-5]
        self.configs = args[:-5]
        
        self.subcircuits = []
        
    def generate_random(self, max_netlists=500, max_attempts=100000):
        self.generated_count = 0
        attempts = 0
        
        while self.generated_count < max_netlists and attempts < max_attempts:
            attempts += 1
            
            # global flow planning
            import random
            
            # 1. signal net assignments
            main_ports = {
                'Vinp': 'I',
                'Vinn': 'I',
                'Voutp': 'O'
            }
            if self.mode == 'differential':
                main_ports['Voutn'] = 'O'
            
            # 2. bias net assignments
            all_bias_nets = [f'Vbiasn{i}' for i in range(self.n_vbiasn)] + \
                            [f'Vbiasp{i}' for i in range(self.n_vbiasp)] + \
                            [f'Ibias{i}' for i in range(self.n_ibias)]
            
            subckt_assignments = [{} for _ in range(len(self.configs))]
            subckt_assignments[0].update(main_ports)
            
            # assign I/O logic
            for net in all_bias_nets:
                # each bias net has 70% chance of being used
                if random.random() < 0.7:
                    num_users = random.randint(1, len(self.configs))
                    users_indices = random.sample(range(len(self.configs)), num_users)
                    
                    if num_users > 1:
                        if random.choice(['external', 'internal']) == 'internal':
                            source_idx = random.choice(users_indices)
                            for idx in users_indices:
                                subckt_assignments[idx][net] = 'O' if idx == source_idx else 'I'
                        else:
                            for idx in users_indices:
                                subckt_assignments[idx][net] = 'I'
                    else:
                        subckt_assignments[users_indices[0]][net] = 'I'
            
            current_subcircuits = []
            success = True
            
            for idx, config in enumerate(self.configs):
                n_nfet, n_pfet, n_res, n_cap = config
                is_main = (idx == 0)
                subckt = Subcircuit(f"Subckt_{idx}", n_nfet, n_pfet, n_res, n_cap, self.mode, 
                                    self.n_vbiasn, self.n_vbiasp, self.n_ibias, self.n_internal_nets, 
                                    is_main=is_main, assigned_ports=subckt_assignments[idx])
                
                if not subckt.generate_structure():
                    success = False
                    break
                current_subcircuits.append(subckt)
            
            if success:
                self.subcircuits = current_subcircuits
                self.generated_count += 1
                self.write_netlist(self.generated_count)
                if self.generated_count % 10 == 0:
                    print(f"Generated {self.generated_count}/{max_netlists} (Attempts: {attempts})")

    def write_netlist(self, index):
        filename = f"{self.mode}{index}.scs"
        filepath = os.path.join(RESULTS_DIR, filename)
        
        global_param_map = {} 
        param_idx = 1
        used_params = set()
        
        all_subckt_defs = []
        instantiations = []
        bias_sources = []
        
        total_fet_num = 0

        bias_drivers = {}
        for subckt in self.subcircuits:
            for net, role in subckt.assigned_ports.items():
                if role == 'O':
                    bias_drivers[net] = subckt
        
        all_used_nets = set()
        for subckt in self.subcircuits:
            all_used_nets.update(subckt.assigned_ports.keys())
            
        bias_sources = []
        for net in sorted(all_used_nets):
            if net in bias_drivers:
                continue
            
            if net.startswith('Ibias'):
                param = f"ibias{net[5:]}"
                bias_sources.append(f"I_{net} ({net} gnd!) isource dc={param} type=dc")
            elif net.startswith('Vbias'):
                param = f"vbias{net[5:].lower()}"
                bias_sources.append(f"V_{net} ({net} gnd!) vsource dc={param} type=dc")

        for subckt in self.subcircuits:
            pairs = subckt.get_pairs()
            sorted_pairs = sorted(pairs, key=lambda x: min(c.name for c in x))
            
            subckt_param_map = {}
            
            for group in sorted_pairs:
                nA = f"nA{param_idx}"
                nB = f"nB{param_idx}"
                for c in group:
                    subckt_param_map[c] = (nA, nB)
                param_idx += 1
                used_params.add(nA)
                used_params.add(nB)
                
            for comp in subckt.components:
                if isinstance(comp, Resistor):
                    idx = comp.name[1:]
                    used_params.add(f"nR{idx}") 
                elif isinstance(comp, Capacitor):
                    idx = comp.name[1:]
                    used_params.add(f"nC{idx}")

            ports = []
            pininfo = []
            for net in sorted(subckt.assigned_ports.keys()):
                ports.append(net)
                role = subckt.assigned_ports[net]
                pininfo.append(f"{net}:{role}")
            
            ports_str = " ".join(ports)
            pininfo_str = " ".join(pininfo)
            
            lines = [f"subckt {subckt.name} {ports_str}"]
            lines.append(f"*.PININFO {pininfo_str}")
            
            lines.extend(subckt.get_netlist_lines(subckt_param_map))
            
            lines.append(f"ends {subckt.name}")
            all_subckt_defs.append("\n".join(lines))
            
            total_fet_num += subckt.num_nfet + subckt.num_pfet
            
            # Instantiate
            inst_ports = []
            for net in ports:
                # All subckt ports now map to global nets of the same name
                inst_ports.append(net)
            
            inst_ports_str = " ".join(inst_ports)
            if len(self.subcircuits) > 1:
                instantiations.append(f"x{subckt.name} {inst_ports_str} {subckt.name}")

        # Generate shared bias sources only for nets that have NO internal driver
        # actually, for bias sources, they are usually supplied externally.
        # But per "if one bias is in one it must be out in another", 
        # it implies internal generation. However, Vsource/Isource are global.
        # If a net has a Vsource, it's driven by that source. 
        # If it's "Out" from a subckt, that subckt is driving it.
        # Rule change: Only generate a top-level source if NO subcircuit is driving it.
        
        if len(self.subcircuits) == 1:
            # Solitary subckt Case: Flatten hierarchy
            subckt = self.subcircuits[0]
            # (Parameters have already been calculated in the loop above)
            core_lines = subckt.get_netlist_lines(subckt_param_map)
            core_netlist = "\n".join(core_lines) + \
                           "\n\n*---Bias Sources---\n" + "\n".join(bias_sources)
        else:
            # Multi-subckt Case
            core_netlist = "\n\n".join(all_subckt_defs) + \
                           "\n\n*---Bias Sources---\n" + "\n".join(bias_sources) + \
                           "\n\n*---Instantiations---\n" + "\n".join(instantiations)
        
        # Ensure all used biases are in the parameters list
        for net in all_used_nets:
            used_params.add(net.lower())
        
        # Parameters
        param_list_tpl = []
        for p in sorted(used_params):
            param_list_tpl.append(f"{p}={{{{{p}}}}}")
        extra_params_tpl = " ".join(param_list_tpl)
        
        # Fill Template
        if self.mode == 'single_ended':
            template = SINGLE_ENDED_TEMPLATE
        else:
            template = DIFFERENTIAL_TEMPLATE
            
        content = template.replace("<<FET_NUM>>", "{{fet_num}}")
        content = content.replace("<<EXTRA_PARAMS>>", extra_params_tpl)
        content = content.replace("<<CORE_NETLIST>>", core_netlist)
        
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
