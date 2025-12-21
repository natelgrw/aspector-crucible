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
    def __init__(self, name, config, mode, start_mm=0, start_r=0, start_c=0, is_main=False, assigned_ports=None):
        # assigned_ports is a dict: {net_name: 'I' or 'O'}
        self.name = name
        self.num_nfet, self.num_pfet, self.num_res, self.num_cap = config
        
        # single ended or differential
        self.mode = mode
        self.is_main = is_main
        self.assigned_ports = assigned_ports if assigned_ports else {}
        
        self.components = []
        self._init_components(start_mm, start_r, start_c)
        
        # fixed nets
        self.fixed_nets = ['vdd!', 'gnd!']
        
        # io nets - only belonging to first main subcircuit
        if self.is_main:
            if mode == 'single_ended':
                self.all_io_nets = ['Vinp', 'Vinn', 'Voutp']
            else:
                self.all_io_nets = ['Vinp', 'Vinn', 'Voutp', 'Voutn']
        else:
            self.all_io_nets = []

    def _init_components(self, start_mm, start_r, start_c):
        mm_idx = start_mm
        for i in range(self.num_nfet):
            self.components.append(Transistor(f"MM{mm_idx}", 'nfet'))
            mm_idx += 1
        for i in range(self.num_pfet):
            self.components.append(Transistor(f"MM{mm_idx}", 'pfet'))
            mm_idx += 1
            
        r_idx = start_r
        for i in range(self.num_res):
            self.components.append(Resistor(f"R{r_idx}"))
            r_idx += 1
            
        c_idx = start_c
        for i in range(self.num_cap):
            self.components.append(Capacitor(f"C{c_idx}"))
            c_idx += 1

    def generate_structure(self, bias_nets, internal_nets, max_attempts=1000):
        # store for internal use
        self.bias_nets = bias_nets
        self.internal_nets = internal_nets

        for attempt in range(max_attempts):
            # reset
            for comp in self.components:
                comp.nets = {}
            
            for comp in self.components:
                if isinstance(comp, Transistor):
                    if comp.type == 'nfet':
                        comp.connect('B', 'gnd!')
                    else:
                        comp.connect('B', 'vdd!')

            # pool of available terminals
            remaining_terms = []
            for comp in self.components:
                terms = ['D', 'G', 'S'] if isinstance(comp, Transistor) else comp.terminals
                for t in terms:
                    remaining_terms.append((comp, t))
            
            random.shuffle(remaining_terms)
            
            assigned_nets = sorted(list(self.assigned_ports.keys()))
            assignments = {}
            
            # map assigned nets to terminals first
            for net in assigned_nets:
                role = self.assigned_ports[net]
                
                # terminal type selection logic
                # Vinn, Vinp, Vbiasp, Vbiasn (input) -> gate
                # vout, ibias, output -> drain or source
                is_gate_only = (net.startswith(('Vinn', 'Vinp', 'Vbias')) and role == 'I')
                is_ds_only = (role == 'O' or net.startswith('Ibias'))
                
                vbiasp = net.startswith('Vbiasp')
                vbiasn = net.startswith('Vbiasn')
                
                selected_idx = -1
                for idx, (comp, term) in enumerate(remaining_terms):
                    # fet restrictions
                    if vbiasp and not (isinstance(comp, Transistor) and comp.type == 'pfet'):
                        continue
                    if vbiasn and not (isinstance(comp, Transistor) and comp.type == 'nfet'):
                        continue
                        
                    # terminal type checks
                    if isinstance(comp, Transistor):
                        if is_gate_only and term != 'G':
                            continue
                        if is_ds_only and term not in ('D', 'S'):
                            continue
                    
                    selected_idx = idx
                    break
                
                if selected_idx != -1:
                    comp, term = remaining_terms.pop(selected_idx)
                    comp.connect(term, net)
                    assignments[(comp, term)] = net
            
            if len(assignments) < len(assigned_nets):
                continue
            
            # randomly assign remaining terminals
            # use nets intended for this subcircuit
            available_nets = self.fixed_nets + self.all_io_nets + list(self.assigned_ports.keys()) + internal_nets
            for comp, term in remaining_terms:
                comp.connect(term, random.choice(available_nets))
                
            if self._is_valid(available_nets):
                return True
        return False

    def _is_valid(self, available_nets):
        # floating net check
        net_counts = {n: 0 for n in available_nets}
        for comp in self.components:
            for t in comp.terminals:
                n = comp.get_net(t)
                if n: net_counts[n] += 1
        
        # internal net usage
        for net in self.internal_nets:
            if net_counts[net] == 1:
                return False
        
        # trivial connections and node accuracy
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
                    
                    # vbiasp/vbiasn type check
                    if n:
                        if n.startswith('Vbiasp') and comp.type != 'pfet':
                            return False
                        if n.startswith('Vbiasn') and comp.type != 'nfet':
                            return False
                        
                        # pininfo role vs terminal check
                        if n in self.assigned_ports:
                            role = self.assigned_ports[n]
                            is_gate_node = (n.startswith(('Vinn', 'Vinp', 'Vbias')) and role == 'I')
                            is_ds_node = (role == 'O' or n.startswith('Ibias'))
                            
                            if is_gate_node and t != 'G':
                                return False
                            if is_ds_node and t not in ('D', 'S'):
                                return False

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

        # ensure assigned ports are used
        # verify pininfo matches connections
        for net, role in self.assigned_ports.items():
            if net_counts.get(net, 0) == 0:
                return False
            
            # check pin role vs connection type
            # I: must connect to g or passive
            # O: must connect to d/s or passive
            is_connected_to_g = False
            is_connected_to_ds = False
            is_connected_to_passive = False
            
            for comp in self.components:
                for t in comp.terminals:
                    if comp.get_net(t) == net:
                        if isinstance(comp, Transistor):
                            if t == 'G':
                                is_connected_to_g = True
                            elif t in ['D', 'S']:
                                is_connected_to_ds = True
                        else:
                            is_connected_to_passive = True
            
            if role == 'I':
                # input must connect to gate or passive
                if not (is_connected_to_g or is_connected_to_passive):
                    return False
            elif role == 'O':
                # output must connect to drain/source or passive
                if not (is_connected_to_ds or is_connected_to_passive):
                    return False
             
        return True

    def get_pairs(self):
        # returns list of sets of paired components
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
                    
                    # same gate and same/symmetric source
                    if c1.get_net('G') == c2.get_net('G'):
                        s1 = c1.get_net('S')
                        s2 = c2.get_net('S')
                        if s1 == s2:
                            is_pair = True
                        elif s1 in sym_nets and sym_nets[s1] == s2:
                            is_pair = True
                        
                    # symmetric connections
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
                nA, nB = param_map[comp]
                lines.append(f"{comp.name} ({p} {n}) resistor r={nA}")
            elif isinstance(comp, Capacitor):
                p = comp.get_net('P')
                n = comp.get_net('N')
                nA, nB = param_map[comp]
                lines.append(f"{comp.name} ({p} {n}) capacitor c={nA}")
        return lines

class NetlistGenerator:
    def __init__(self, configs, mode, n_vbiasn, n_vbiasp, n_ibias, n_internal_nets):
        self.configs = configs
        self.mode = mode
        self.n_vbiasn = n_vbiasn
        self.n_vbiasp = n_vbiasp
        self.n_ibias = n_ibias
        self.n_internal_nets = n_internal_nets
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
            
            # subckt 0 is main, must contain vin/vout
            # generalized bias distribution
            # - each used bias net is i in exactly one subcircuit m
            # - each used bias net is o in at most one subcircuit n
            # - if both exist, m < n
            # - all bias nodes in subckt 0 are i
            
            used_bias_nets = []
            for net in all_bias_nets:
                if random.random() < 0.7:
                    used_bias_nets.append(net)
                    # all are i in subckt 0
                    subckt_assignments[0][net] = 'I'
            
            if len(self.configs) > 1 and used_bias_nets:
                # optionally assign o in higher subcircuit
                for net in used_bias_nets:
                    if random.random() < 0.6:
                        # pick subcircuit j where 0 < j
                        target_j = random.randint(1, len(self.configs) - 1)
                        subckt_assignments[target_j][net] = 'O'
                
                # auxiliary subcircuits drive at least one bias
                for j in range(1, len(self.configs)):
                    if not any(r == 'O' for r in subckt_assignments[j].values()):
                        non_driven = [n for n in used_bias_nets if not any(subckt_assignments[k].get(n) == 'O' for k in range(1, len(self.configs)))]
                        if non_driven:
                            net = random.choice(non_driven)
                            subckt_assignments[j][net] = 'O'
                        else:
                            # add new bias to subckt 0 and drive here
                            available = [n for n in all_bias_nets if n not in used_bias_nets]
                            if available:
                                net = random.choice(available)
                                used_bias_nets.append(net)
                                subckt_assignments[0][net] = 'I'
                                subckt_assignments[j][net] = 'O'

            all_internal_nets = [f"net{i}" for i in range(self.n_internal_nets)]

            current_subcircuits = []
            success = True
            
            # track global naming indices
            global_mm_idx = 0
            global_r_idx = 0
            global_c_idx = 0

            for idx, config in enumerate(self.configs):
                is_main = (idx == 0)
                subckt = Subcircuit(f"Subckt_{idx}", config, self.mode, 
                                    start_mm=global_mm_idx, 
                                    start_r=global_r_idx, 
                                    start_c=global_c_idx,
                                    is_main=is_main, assigned_ports=subckt_assignments[idx])
                
                # update global indices
                global_mm_idx += (subckt.num_nfet + subckt.num_pfet)
                global_r_idx += subckt.num_res
                global_c_idx += subckt.num_cap
                
                if not subckt.generate_structure(all_bias_nets, all_internal_nets):
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
            
            if net.startswith('Ibias'):
                param = f"ibias{net[5:]}"
                bias_sources.append(f"I_{net} ({net} gnd!) isource dc={param} type=dc")
            elif net.startswith('Vbias'):
                param = f"vbias{net[5:].lower()}"
                bias_sources.append(f"V_{net} ({net} gnd!) vsource dc={param} type=dc")

        param_idx = 0
        r_idx = 0
        c_idx = 0

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
                    param_name = f"nR{r_idx}"
                    subckt_param_map[comp] = (param_name, None)
                    used_params.add(param_name)
                    r_idx += 1
                elif isinstance(comp, Capacitor):
                    param_name = f"nC{c_idx}"
                    subckt_param_map[comp] = (param_name, None)
                    used_params.add(param_name)
                    c_idx += 1

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
            
            # instantiate
            inst_ports = []
            for net in ports:
                # map subckt ports to global nets
                inst_ports.append(net)
            
            inst_ports_str = " ".join(inst_ports)
            if len(self.subcircuits) > 1:
                instantiations.append(f"x{subckt.name} {inst_ports_str} {subckt.name}")
        
        if len(self.subcircuits) == 1:
            # single subcircuit case
            subckt = self.subcircuits[0]
            core_lines = subckt.get_netlist_lines(subckt_param_map)
            
            # formatting title and pininfo
            net_list = " ".join(sorted(subckt.assigned_ports.keys()))
            pin_list = " ".join([f"{net}:{role}" for net, role in sorted(subckt.assigned_ports.items())])
            
            core_netlist = f"* Circuit_{index} {net_list}\n*.PININFO {pin_list}\n" + \
                           "\n".join(core_lines) + \
                           "\n\n*---Bias Sources---\n" + "\n".join(bias_sources)
        else:
            # multi-subcircuit case
            core_netlist = "\n\n".join(all_subckt_defs) + \
                           "\n\n*---Bias Sources---\n" + "\n".join(bias_sources) + \
                           "\n\n*---Instantiations---\n" + "\n".join(instantiations)
        
        # ensure only bias nets are in parameters
        for net in all_used_nets:
            if net.startswith('Ibias') or net.startswith('Vbias'):
                used_params.add(net.lower())
        
        # parameters
        param_list_tpl = []
        for p in sorted(used_params):
            param_list_tpl.append(f"{p}={{{{{p}}}}}")
        extra_params_tpl = " ".join(param_list_tpl)
        
        # fill template
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
