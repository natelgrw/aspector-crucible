
import random
import networkx as nx
from components import Component, Transistor, Resistor, Capacitor

class NetlistParser:
    def __init__(self, filepath):
        self.filepath = filepath
        self.content = ""
        self.topology_block = ""
        self.pre_topology = ""
        self.post_topology = ""
        self.circuit_name = ""
        self.ports = []
        self.pininfo = ""
        self.components = []
        self.new_parameters = {}
        self.next_nA = 1
        self.next_nB = 1
        self.next_nR = 1
        self.next_nC = 1
        
    def parse(self):
        with open(self.filepath, 'r') as f:
            self.content = f.read()
            
        parts = self.content.split("*--- TOPOLOGY ---*")
        if len(parts) != 2:
            raise ValueError("File does not contain exactly one *--- TOPOLOGY ---* block")
            
        self.pre_topology = parts[0] + "*--- TOPOLOGY ---*\n\n"
        
        # Parse existing parameters to find max nA/nB
        self._parse_existing_parameters()
        
        topology_part = parts[1]
        if "*--- TESTBENCH ---*" in topology_part:
            topo_split = topology_part.split("*--- TESTBENCH ---*")
            self.topology_block = topo_split[0]
            self.post_topology = "\n*--- TESTBENCH ---*" + topo_split[1]
        else:
            self.topology_block = topology_part
            self.post_topology = ""
            
        self._parse_topology_block()

    def _parse_existing_parameters(self):
        # Look for "parameters ..." line in pre_topology
        lines = self.pre_topology.split('\n')
        for line in lines:
            if line.strip().startswith('parameters '):
                tokens = line.strip().split()
                for t in tokens[1:]: # Skip 'parameters' keyword
                    if '=' in t:
                        k, v = t.split('=')
                        # Check for nA{N} or nB{N}
                        if k.startswith('nA'):
                            try:
                                val = int(k[2:])
                                if val >= self.next_nA: self.next_nA = val + 1
                            except ValueError: pass
                        elif k.startswith('nB'):
                            try:
                                val = int(k[2:])
                                if val >= self.next_nB: self.next_nB = val + 1
                            except ValueError: pass
                        elif k.startswith('nR'):
                            try:
                                val = int(k[2:])
                                if val >= self.next_nR: self.next_nR = val + 1
                            except ValueError: pass
                        elif k.startswith('nC'):
                            try:
                                val = int(k[2:])
                                if val >= self.next_nC: self.next_nC = val + 1
                            except ValueError: pass

    def get_next_param_name(self, prefix='nA'):
        if prefix == 'nA':
            name = f"nA{self.next_nA}"
            self.next_nA += 1
            return name
        elif prefix == 'nB':
            name = f"nB{self.next_nB}"
            self.next_nB += 1
            return name
        elif prefix == 'nR':
            name = f"nR{self.next_nR}"
            self.next_nR += 1
            return name
        elif prefix == 'nC':
            name = f"nC{self.next_nC}"
            self.next_nC += 1
            return name
        else:
            # Default/Fallback
            idx = len(self.new_parameters)
            return f"{prefix}_{idx}"

    def add_parameter(self, name, value):
        self.new_parameters[name] = value

    def _parse_topology_block(self):
        lines = self.topology_block.strip().split('\n')
        self.components = []
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            if line.startswith("*---") and line.endswith("---*"):
                content = line[4:-4].strip()
                tokens = content.split()
                if len(tokens) > 0:
                    self.circuit_name = tokens[0]
                    self.ports = tokens[1:]
            elif line.startswith("*.PININFO"):
                self.pininfo = line
            elif line.startswith("*"):
                continue
            else:
                self._parse_component(line)

    def _parse_component(self, line):
        tokens = line.split()
        name = tokens[0]
        
        if name.startswith('M') or name.startswith('MM'):
            # Transistor: Name D G S B Type Params...
            d, g, s, b = tokens[1:5]
            type_ = tokens[5]
            params = " ".join(tokens[6:])
            comp = Transistor(name, type_, raw_params=params)
            comp.connect('D', d)
            comp.connect('G', g)
            comp.connect('S', s)
            comp.connect('B', b)
            self.components.append(comp)
            
        elif name.startswith('C') or name.startswith('CC'):
            self._parse_passive(name, tokens, Capacitor, 'capacitor')

        elif name.startswith('R'):
             self._parse_passive(name, tokens, Resistor, 'resistor')

    def _parse_passive(self, name, tokens, cls, type_keyword):
        # Handles both "C1 n1 n2 ..." and "C1 (n1 n2) ..."
        # and "C1 ... capacitor ..." pattern
        
        remaining = tokens[1:]
        idx = 0
        nodes = []
        
        # Check for parens (n1 n2)
        if remaining[0].startswith('('):
            nodes_str = ""
            while idx < len(remaining):
                nodes_str += remaining[idx]
                if remaining[idx].endswith(')'):
                    idx += 1
                    break
                idx += 1
            nodes_str = nodes_str.replace('(', '').replace(')', '')
            nodes = nodes_str.split()
        else:
            # No parens: n1 n2 type ...
            # Assume 2 nodes
            nodes = [remaining[0], remaining[1]]
            idx = 2
            
        if len(nodes) != 2:
            return # Error or unknown format
            
        p, n = nodes[0], nodes[1]
        
        # Check for type keyword (capacitor/resistor) to find where params start
        # Usually it follows nodes.
        params = ""
        # Search for keyword starting from current idx
        # But based on typical .scs, it's: Name Nodes Type Params
        # or Name Nodes Params (if type implicit? but here we see explicit type)
        
        # If the next token is the type keyword, skip it
        if idx < len(remaining) and remaining[idx] == type_keyword:
             params = " ".join(remaining[idx+1:])
        else:
             # Just join remaining?
             params = " ".join(remaining[idx:])

        comp = cls(name, raw_params=params)
        comp.connect('P', p)
        comp.connect('N', n)
        self.components.append(comp)

    def add_parameter(self, name, value):
        self.new_parameters[name] = value

    def regenerate(self, new_circuit_name=None):
        cname = new_circuit_name if new_circuit_name else self.circuit_name
        new_topology = []
        header = f"*--- {cname} {' '.join(self.ports)} ---*"
        new_topology.append(header)
        
        if self.pininfo:
            new_topology.append(self.pininfo)
            
        for comp in self.components:
            line = ""
            if isinstance(comp, Transistor):
                d = comp.get_net('D')
                g = comp.get_net('G')
                s = comp.get_net('S')
                b = comp.get_net('B')
                line = f"{comp.name} {d} {g} {s} {b} {comp.type} {comp.raw_params}"
            elif isinstance(comp, Resistor):
                 p = comp.get_net('P')
                 n = comp.get_net('N')
                 line = f"{comp.name} {p} {n} resistor {comp.raw_params}"
            elif isinstance(comp, Capacitor):
                 p = comp.get_net('P')
                 n = comp.get_net('N')
                 line = f"{comp.name} {p} {n} capacitor {comp.raw_params}"
            new_topology.append(line)
            
        # Handle Parameters Injection
        final_pre_topology = self.pre_topology
        
        # 1. Parse existing parameters line
        lines = final_pre_topology.split('\n')
        new_lines = []
        
        all_params = {}
        other_params_order = [] 
        
        existing_param_line_idx = -1
        
        for idx, line in enumerate(lines):
            if line.strip().startswith('parameters '):
                existing_param_line_idx = idx
                content = line.strip()[11:]
                tokens = content.split()
                for t in tokens:
                    if '=' in t:
                        k, v = t.split('=', 1)
                        if k not in all_params:
                             all_params[k] = v
                             if not (k.startswith('nA') or k.startswith('nB')):
                                 other_params_order.append(k)
                break
        
        # 2. Merge new parameters
        if self.new_parameters:
             for k, v in self.new_parameters.items():
                 if k.startswith('nA') or k.startswith('nB') or k.startswith('nR') or k.startswith('nC'):
                      all_params[k] = f"{{{{{k}}}}}"
                 else:
                      all_params[k] = v
                      if k not in other_params_order:
                           other_params_order.append(k)
                           
        # 3. Identify USED nA/nB/nR/nC parameters
        used_keys = set()
        for comp in self.components:
             # Scan raw_params for nA... or nB... or nR... or nC...
             # Tokens could be l=nA1, nfin=nB2, or just values
             if not comp.raw_params: continue
             tokens = comp.raw_params.replace('=', ' ').split()
             for t in tokens:
                  if t.startswith('nA') or t.startswith('nB') or t.startswith('nR') or t.startswith('nC'):
                       # It might be nA1 or nA1) or nA1} etc (unlikely but safe to strip)
                       # Basic cleaning
                       clean_t = "".join([c for c in t if c.isalnum()])
                       if clean_t in all_params:
                            used_keys.add(clean_t)
                            
        # 4. Sort nA, nB, nR, nC (ONLY USED ONES)
        nA_keys = [k for k in all_params.keys() if k.startswith('nA') and k in used_keys]
        nB_keys = [k for k in all_params.keys() if k.startswith('nB') and k in used_keys]
        nR_keys = [k for k in all_params.keys() if k.startswith('nR') and k in used_keys]
        nC_keys = [k for k in all_params.keys() if k.startswith('nC') and k in used_keys]
        
        def sort_key(k):
            try:
                return int(k[2:])
            except ValueError:
                return 999999
                
        nA_keys = sorted(nA_keys, key=sort_key)
        nB_keys = sorted(nB_keys, key=sort_key)
        nR_keys = sorted(nR_keys, key=sort_key)
        nC_keys = sorted(nC_keys, key=sort_key)
        
        # 5. Reconstruct Parameter String
        new_param_parts = []
        for k in other_params_order:
             new_param_parts.append(f"{k}={all_params[k]}")
             
        for k in nA_keys:
             new_param_parts.append(f"{k}={all_params[k]}")
             
        for k in nB_keys:
             new_param_parts.append(f"{k}={all_params[k]}")

        for k in nR_keys:
             new_param_parts.append(f"{k}={all_params[k]}")

        for k in nC_keys:
             new_param_parts.append(f"{k}={all_params[k]}")
             
        if new_param_parts:
             new_param_line = "parameters " + " ".join(new_param_parts)
             if existing_param_line_idx != -1:
                  lines[existing_param_line_idx] = new_param_line
             else:
                  # Inject before topology if no parameters line existed
                  lines.append(new_param_line)
             
        final_pre_topology = "\n".join(lines)

        # Handle Save Command Update
        final_post_topology = self.post_topology
        if "save V0:p" in final_post_topology:
            # Find all transistors in current component list
            transistors = [c for c in self.components if isinstance(c, Transistor)]
            
            # Base save list
            save_cmd = "save V0:p Voutp Vinp Vinn"
            
            # Append transistor operating points for ALL valid transistors
            for t in transistors:
                save_cmd += f" {t.name}:gm {t.name}:vgs {t.name}:vds {t.name}:ids {t.name}:region"
            
            # Replace existing save line
            lines = final_post_topology.split('\n')
            new_lines = []
            for l in lines:
                if l.strip().startswith('save ') and 'V0:p' in l:
                    new_lines.append(save_cmd)
                else:
                    new_lines.append(l)
            final_post_topology = "\n".join(new_lines)
            
        return final_pre_topology + "\n".join(new_topology) + "\n\n" + final_post_topology

class CircuitGraph:
    def __init__(self, components):
        self.components = components
        self.graph = nx.Graph()
        self._build_graph()
        
    def _build_graph(self):
        self.graph.clear()
        for comp in self.components:
            self.graph.add_node(comp, type='component', obj=comp)
            for terminal, net in comp.connections.items():
                if not self.graph.has_node(net):
                    self.graph.add_node(net, type='net')
                self.graph.add_edge(comp, net, terminal=terminal)
                
    def get_nets(self):
        return [n for n, d in self.graph.nodes(data=True) if d.get('type') == 'net']

class ErrorInjector:
    def __init__(self, parser):
        self.parser = parser
        self.components = parser.components
        self.graph = CircuitGraph(self.components)
        
    def _rebuild_graph(self):
        self.graph = CircuitGraph(self.components)
        
    def _get_new_net_name(self):
        # Find highest net{N}
        max_n = 0
        existing_nets = self.graph.get_nets()
        for net in existing_nets:
            if net.startswith("net"):
                try:
                    val = int(net[3:])
                    if val > max_n:
                        max_n = val
                except ValueError:
                    pass
        return f"net{max_n + 1}"

    def _add_param(self, name_hint, value):
        # Legacy/Generic param adder
        idx = len(self.parser.new_parameters)
        pname = f"pfault_{name_hint}_{idx}"
        self.parser.add_parameter(pname, value)
        return pname

    def _add_geometry_param(self, param_type, value):
        # Specific adder for nA/nB series
        if param_type == 'l':
            pname = self.parser.get_next_param_name('nA')
        elif param_type == 'nfin' or param_type == 'w':
            pname = self.parser.get_next_param_name('nB')
        else:
            return self._add_param(param_type, value)
            
        self.parser.add_parameter(pname, value)
        return pname

    def _update_param(self, existing_params, key, new_val_name):
        # Replaces key=old_val with key=new_val_name
        # Or appends key=new_val_name if not found
        tokens = existing_params.split()
        new_tokens = []
        found = False
        
        for t in tokens:
            if t.startswith(key + "="):
                new_tokens.append(f"{key}={new_val_name}")
                found = True
            else:
                new_tokens.append(t)
                
        if not found:
            new_tokens.append(f"{key}={new_val_name}")
            
        return " ".join(new_tokens)

    def inject(self, error_vector):
        error_map = {
            0: self.error_non_modal,         # 240
            1: self.error_source_absent,     # 241
            2: self.error_galvanic_island,   # 242
            3: self.error_ideal_short,       # 243
            4: self.error_ideal_open,        # 244
            5: self.error_kcl_conflict,      # 245
            6: self.error_kvl_conflict,      # 246
            7: self.error_port_dangling,     # 247
            8: self.warning_bias_path,       # 248
            9: self.warning_symmetry,        # 249
            10: self.warning_loop_phase,     # 250
            11: self.warning_impedance,      # 251
            12: self.warning_stack,          # 252
            13: self.warning_steering,       # 253
            14: self.warning_isolation,      # 254
            15: self.warning_dropout         # 255
        }
        
        for bit, func in error_map.items():
            if (error_vector >> bit) & 1:
                print(f"Injecting Error Bit {bit} (ID {240+bit})")
                try:
                    func()
                except Exception as e:
                    print(f"Failed to inject error {240+bit}: {e}")

    # Helper for multi-injection
    def _get_random_targets(self, candidates):
        if not candidates: return []
        # Random number of targets: 1 to len(candidates)
        count = random.randint(1, len(candidates))
        return random.sample(candidates, count)

    # 240
    def error_non_modal(self):
        comps = [c for c in self.components if isinstance(c, Transistor)]
        targets = self._get_random_targets(comps)
        for c in targets:
            new_type = 'nfet' if c.type == 'pfet' else 'pfet'
            c.type = new_type
            print(f"  Non-Modal Error: Swapped {c.name} type to {new_type}")

    # 241
    def error_source_absent(self):
        bias_nets = [n for n in self.graph.get_nets() if n.startswith('Vbias') or n.startswith('Ibias')]
        if not bias_nets: return
        
        target_nets = self._get_random_targets(bias_nets)
        for target_net in target_nets:
            connected_comps = []
            for n, neighbors in self.graph.graph.adj.items():
                if n == target_net:
                    for comp in neighbors:
                        connected_comps.append(comp)
            
            if connected_comps:
                targets = self._get_random_targets(connected_comps)
                for comp in targets:
                    new_net = self._get_new_net_name()
                    terms_to_break = [t for t, n in comp.connections.items() if n == target_net]
                    for t in terms_to_break:
                        comp.connect(t, new_net)
                        print(f"  Source Absent: Disconnected {target_net} from {comp.name}:{t} to {new_net}")
                self._rebuild_graph()

    # 242 - COMPONENT REMOVAL (BYPASS)
    def error_galvanic_island(self):
        targets = self._get_random_targets(self.components)
        for comp in targets:
            # Logic: Short "through" the component to bypass it, then disconnect
            if isinstance(comp, Transistor):
                # Short Drain to Source
                d = comp.get_net('D')
                s = comp.get_net('S')
                print(f"  Component Removal: Bypassing {comp.name} (Shorting {d} to {s})")
                
                # Perform the short
                if d != s:
                     self._short_nets(d, s)
                
                # Now effectively remove the component by disconnecting all terminals
                for term in comp.terminals:
                    comp.connect(term, self._get_new_net_name())
            
            elif isinstance(comp, (Resistor, Capacitor)):
                # Short P to N
                p = comp.get_net('P')
                n = comp.get_net('N')
                print(f"  Component Removal: Bypassing {comp.name} (Shorting {p} to {n})")
                if p != n:
                    self._short_nets(p, n)
                
                for term in comp.terminals:
                    comp.connect(term, self._get_new_net_name())

        self._rebuild_graph()

    def _short_nets(self, net1, net2):
        # Move all connections from net1 to net2
        for c in self.components:
            for t, n in c.connections.items():
                if n == net1:
                    c.connect(t, net2)

    # 243
    def error_ideal_short(self):
        nets = self.graph.get_nets()
        if len(nets) < 2: return
        count = random.randint(1, max(1, len(nets)//4))
        for _ in range(count):
            if len(nets) < 2: break
            n1, n2 = random.sample(nets, 2)
            if n1 == n2: continue
            print(f"  Ideal Short: Shorting {n2} to {n1}")
            for comp in self.components:
                for t, net in comp.connections.items():
                    if net == n2:
                        comp.connect(t, n1)
            # Update nets list? simple way is just proceed, redundancy is fine
            self._rebuild_graph()

    # 244
    def error_ideal_open(self):
        targets = self._get_random_targets(self.components)
        for comp in targets:
            term_targets = self._get_random_targets(comp.terminals)
            for term in term_targets:
                old_net = comp.connections.get(term)
                new_net = self._get_new_net_name()
                comp.connect(term, new_net)
                print(f"  Ideal Open: Opened {comp.name}:{term} (was {old_net}, now {new_net})")
        self._rebuild_graph()

    # 245
    def error_kcl_conflict(self):
        # Target random nets, not just Voutp
        nets = self.graph.get_nets()
        targets = self._get_random_targets(nets)
        for t_net in targets:
            conflict_net = 'vdd!' if random.random() > 0.5 else 'gnd!'
            print(f"  KCL Conflict: Shorting {t_net} to {conflict_net}")
            for comp in self.components:
                 for t, net in comp.connections.items():
                    if net == t_net:
                        comp.connect(t, conflict_net)
        self._rebuild_graph()

    # 246
    def error_kvl_conflict(self):
        comps = [c for c in self.components if isinstance(c, Transistor)]
        targets = self._get_random_targets(comps)
        for c in targets:
            net_s = c.get_net('S')
            c.connect('D', net_s)
            print(f"  KVL Conflict: Shorted D-S of {c.name}")
        self._rebuild_graph()

    # 247
    def error_port_dangling(self):
        if not self.parser.ports: return
        targets = self._get_random_targets(self.parser.ports)
        for port in targets:
            new_net = self._get_new_net_name()
            print(f"  Dangling Port: Disconnecting internals from {port} to {new_net}")
            for comp in self.components:
                for t, net in comp.connections.items():
                    if net == port:
                        comp.connect(t, new_net)
        self._rebuild_graph()

    # Warnings
    def warning_bias_path(self):
        diode_connected = []
        for c in self.components:
            if isinstance(c, Transistor):
                if c.get_net('G') == c.get_net('D'):
                    diode_connected.append(c)
        
        if diode_connected:
            targets = self._get_random_targets(diode_connected)
            for c in targets:
                print(f"  Bias Path Warning: Shorted diode-connected {c.name} G/D to gnd!")
                c.connect('G', 'gnd!')
                c.connect('D', 'gnd!')
            self._rebuild_graph()
        else:
            self.error_source_absent() # Already randomized

    def warning_symmetry(self):
        comps = [c for c in self.components if isinstance(c, Transistor)]
        if not comps: return
        
        all_param_values = []
        for c in comps:
             tokens = c.raw_params.split()
             for t in tokens:
                 if '=' in t:
                     k, v = t.split('=')
                     all_param_values.append(v)
        all_param_values = list(set(all_param_values))
        
        if len(all_param_values) < 2:
            targets = self._get_random_targets(comps)
            for c in targets:
                # Use geometry param
                p_m = self._add_geometry_param('m', 2) # m is not geometry strictly, but uses default
                c.raw_params = self._update_param(c.raw_params, 'm', p_m)
                print(f"  Symmetry Warning (Fallback): Modified {c.name} with m={p_m}")
            return

        targets = self._get_random_targets(comps)
        for c in targets:
            tokens = c.raw_params.split()
            candidates = []
            for i, t in enumerate(tokens):
                if '=' in t:
                    k, v = t.split('=')
                    candidates.append((i, k, v))
            
            if candidates:
                idx, k, v = random.choice(candidates)
                options = [val for val in all_param_values if val != v]
                
                # Determine param type for geometry prefix
                if k == 'l':
                     p_scramble = self._add_geometry_param('l', '100n') # val is dummy, just needs name
                     # We reuse val if possible, but here we want to scramble to existing option
                     # Actually we want a new parameter holding the scrambled value
                     # The value comes from options.
                     pass
                
                if options:
                    new_val = random.choice(options)
                    
                    if k == 'l' or k == 'nfin':
                         p_scramble = self._add_geometry_param(k, new_val)
                    else:
                         p_scramble = self._add_param(f'sym_{k}', new_val)
                         
                    c.raw_params = self._update_param(c.raw_params, k, p_scramble)
                    print(f"  Symmetry Warning: Scrambled {c.name} {k}={v} to {k}={p_scramble}")
                else:
                     p_m = self._add_param('sym_m', 2)
                     c.raw_params = self._update_param(c.raw_params, 'm', p_m)
                     print(f"  Symmetry Warning (Fallback): Modified {c.name} with m={p_m}")
            else:
                 p_m = self._add_param('sym_m', 2)
                 c.raw_params = self._update_param(c.raw_params, 'm', p_m)
                 print(f"  Symmetry Warning (Fallback): Modified {c.name} with m={p_m}")

    def warning_loop_phase(self):
        # Approach 1: Global Swap (50% chance)
        if random.random() > 0.5:
            if 'Vinp' in self.parser.ports and 'Vinn' in self.parser.ports:
                print("  Loop Phase Warning: Swapping Vinp and Vinn")
                for comp in self.components:
                    replacements = {}
                    for t, net in comp.connections.items():
                        if net == 'Vinp':
                            replacements[t] = 'Vinn'
                        elif net == 'Vinn':
                            replacements[t] = 'Vinp'
                    for t, new_net in replacements.items():
                        comp.connect(t, new_net)
        
        # Approach 2: Local G-D Swaps (Random transistors)
        comps = [c for c in self.components if isinstance(c, Transistor)]
        targets = self._get_random_targets(comps)
        for comp in targets:
            g = comp.get_net('G')
            d = comp.get_net('D')
            comp.connect('G', d)
            comp.connect('D', g)
            print(f"  Loop Phase Warning: Swapped G-D on {comp.name}")
        self._rebuild_graph()

    def warning_impedance(self):
        # Add random number of low resistance paths
        count = random.randint(1, 5)
        for _ in range(count):
            target_net = random.choice(self.graph.get_nets())
            # Use nR parameter
            p_res = self.parser.get_next_param_name('nR')
            self.parser.add_parameter(p_res, 1) # Value is template anyway, but need to register it
            
            new_res = Resistor(f"R_fault_{random.randint(0,999)}", raw_params=f"r={p_res}")
            new_res.connect('P', target_net)
            new_res.connect('N', 'gnd!')
            self.components.append(new_res)
            print(f"  Impedance Warning: Added {p_res} (1 Ohm) resistor from {target_net} to gnd!")
        self._rebuild_graph()

    def warning_stack(self):
        candidates = []
        for c in self.components:
            if isinstance(c, Transistor):
                s_net = c.get_net('S')
                neighbors = self.graph.graph[s_net]
                for n in neighbors:
                    if isinstance(n, Transistor) and n != c:
                        edge_data = self.graph.graph.get_edge_data(n, s_net)
                        if edge_data and edge_data.get('terminal') == 'D':
                            candidates.append(c)
                            break
        
        targets = self._get_random_targets(candidates)
        if targets:
            for c in targets:
                print(f"  Stack Warning: Shorting Cascode Device {c.name} (D-S)")
                c.connect('D', c.get_net('S'))
            self._rebuild_graph()
        else:
            self.error_kvl_conflict()

    def warning_steering(self):
        comps = [c for c in self.components if isinstance(c, Transistor)]
        targets = self._get_random_targets(comps)
        for c in targets:
            p_nfin = self._add_geometry_param('nfin', 1)
            c.raw_params = self._update_param(c.raw_params, 'nfin', p_nfin)
            print(f"  Steering Warning: Set nfin={p_nfin} on {c.name}")

    # 254 - COMPONENT INSERTION (Series & Random)
    def warning_isolation(self):
        # Determine number of insertions dynamically based on circuit complexity
        # e.g., 1 to 1/3 of component count, minimum 1
        n_comps = len(self.components)
        max_insertions = max(1, n_comps // 3)
        count = random.randint(1, max_insertions)
        
        print(f"  Insertion Warning: Injecting {count} extra components...")

        for _ in range(count):
             mode = random.choices(['series', 'random'], weights=[0.6, 0.4])[0]
             
             if mode == 'series':
                 # Series Insertion: Pick a net, split it, insert component
                 nets = self.graph.get_nets()
                 target_net = random.choice(nets)
                 
                 # Find components connected to this net
                 connected_terminals = []
                 for c in self.components:
                     for t, n in c.connections.items():
                         if n == target_net:
                             connected_terminals.append((c, t))
                 
                 if not connected_terminals: continue
                 
                 random.shuffle(connected_terminals)
                 split_point = random.randint(1, len(connected_terminals))
                 if len(connected_terminals) > 1:
                     split_point = len(connected_terminals) // 2
                 
                 moved_contacts = connected_terminals[split_point:]
                 if not moved_contacts: 
                      pass 
                 
                 new_net_prime = self._get_new_net_name()
                 for c, t in moved_contacts:
                     c.connect(t, new_net_prime)
                     
                 # Insert Component bridging target_net and new_net_prime
                 comp_type = random.choice(['res', 'cap', 'mos'])
                 
                 if comp_type == 'res':
                     name = f"R_ins_{random.randint(0,9999)}"
                     p_val = self.parser.get_next_param_name('nR')
                     self.parser.add_parameter(p_val, '1k')
                     
                     new_comp = Resistor(name, raw_params=f"r={p_val}")
                     new_comp.connect('P', target_net)
                     new_comp.connect('N', new_net_prime)
                     print(f"  Insertion (Series): Added {name} into {target_net}")
                     
                 elif comp_type == 'cap':
                     name = f"C_ins_{random.randint(0,9999)}"
                     p_val = self.parser.get_next_param_name('nC')
                     self.parser.add_parameter(p_val, '100f')
                     
                     new_comp = Capacitor(name, raw_params=f"c={p_val}")
                     new_comp.connect('P', target_net)
                     new_comp.connect('N', new_net_prime)
                     print(f"  Insertion (Series): Added {name} into {target_net}")
                     
                 elif comp_type == 'mos':
                     name = f"M_ins_{random.randint(0,9999)}"
                     p_l = self._add_geometry_param('l', '100n')
                     p_nf = self._add_geometry_param('nfin', '4')
                     new_comp = Transistor(name, "nfet", raw_params=f"l={p_l} nfin={p_nf}")
                     # Pass gate style
                     new_comp.connect('D', target_net)
                     new_comp.connect('S', new_net_prime)
                     new_comp.connect('G', 'vdd!') # On
                     new_comp.connect('B', 'gnd!')
                     print(f"  Insertion (Series): Added {name} (PassGate) into {target_net}")
                 
                 self.components.append(new_comp)

             else:
                 # Random Insertion
                 nets = self.graph.get_nets()
                 if len(nets) < 4: continue
                 
                 name = f"M_chaos_{random.randint(0,9999)}"
                 p_l = self._add_geometry_param('l', '100n')
                 p_nf = self._add_geometry_param('nfin', '4')
                 new_comp = Transistor(name, "nfet", raw_params=f"l={p_l} nfin={p_nf}")
                 
                 # Pick 4 random nets
                 d, g, s, b = random.sample(nets, 4)
                 new_comp.connect('D', d)
                 new_comp.connect('G', g)
                 new_comp.connect('S', s)
                 new_comp.connect('B', b)
                 
                 self.components.append(new_comp)
                 print(f"  Insertion (Random): Added {name} connected to {d}, {g}, {s}, {b}")

        self._rebuild_graph()

    def warning_dropout(self):
        comps = [c for c in self.components if isinstance(c, Transistor)]
        targets = self._get_random_targets(comps)
        for c in targets:
            new_net = self._get_new_net_name()
            c.connect('B', new_net)
            print(f"  Dropout Warning: Floated Body of {c.name} to {new_net}")
            self._rebuild_graph()
