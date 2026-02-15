
import argparse
import sys
import os
import ast
import random
from circuit_breaker import NetlistParser, ErrorInjector

def main():
    parser = argparse.ArgumentParser(description="Circuit Breaker: Inject errors into analog netlists.")
    parser.add_argument("input_file", help="Path to the input .scs netlist file.")
    # Make output_path optional, default to "results"
    parser.add_argument("output_path", nargs='?', default="results", help="Path to save the modified .scs netlist file (or directory for batch). Defaults to 'results/'.")
    parser.add_argument("--error_vector", type=str, help="Single 16-bit error vector (integer or binary string).")
    parser.add_argument("--batch", type=str, help="List of tuples for batch generation: '[(count, vector), ...]'")
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility. If set, each task uses seed + task_index.")
    
    args = parser.parse_args()
    
    input_path = os.path.abspath(args.input_file)
    output_abs_path = os.path.abspath(args.output_path)
    
    if not os.path.exists(input_path):
        print(f"Error: Input file '{input_path}' not found.")
        sys.exit(1)

    # Determine mode: Single or Batch
    tasks = [] # List of (output_file, vector)
    
    if args.batch:
        try:
            batch_list = ast.literal_eval(args.batch)
            if not isinstance(batch_list, list):
                raise ValueError("Batch argument must be a list of tuples.")
            
            # For batch, output_path is treated as a directory
            output_dir = output_abs_path
            if not os.path.isdir(output_dir):
                 os.makedirs(output_dir, exist_ok=True)

            base_name = os.path.splitext(os.path.basename(input_path))[0]
            
            for item in batch_list:
                # Handle tuple unpacking with optional start_index
                start_index = 0
                if len(item) == 2:
                    count, vec_raw = item
                elif len(item) == 3:
                    count, vec_raw, start_index = item
                else:
                    print(f"Skipping invalid batch item (must be len 2 or 3): {item}")
                    continue

                # Parse vector
                if isinstance(vec_raw, str):
                    clean_vec = vec_raw.replace('_', '')
                    if vec_raw.startswith("0b"):
                        vector = int(vec_raw, 2)
                    elif all(c in '01' for c in clean_vec) and len(clean_vec) > 1:
                        # Heuristic: If it contain ONLY 0s and 1s and is > 1 char, assume binary
                         vector = int(clean_vec, 2)
                    else:
                        try:
                            vector = int(vec_raw)
                        except:
                            print(f"Skipping invalid vector: {vec_raw}")
                            continue
                elif isinstance(vec_raw, int):
                    vector = vec_raw
                else:
                    print(f"Skipping invalid vector type: {type(vec_raw)}")
                    continue
                
                # Format binary string 16-bit
                bin_full = f"{vector:016b}"
                # Insert underscore after 8th bit: 12345678_12345678
                binary_str = f"{bin_full[:8]}_{bin_full[8:]}"
                
                for i in range(start_index, start_index + count):
                    filename = f"{base_name}_{binary_str}_{i}.scs"
                    full_path = os.path.join(output_dir, filename)
                    tasks.append((full_path, vector))
                    
        except Exception as e:
            print(f"Error parsing batch argument: {e}")
            sys.exit(1)
            
    elif args.error_vector:
        # Single mode
        try:
            vec_raw = args.error_vector
            if isinstance(vec_raw, str):
                clean_vec = vec_raw.replace('_', '')
                if vec_raw.startswith("0b"):
                    vector = int(vec_raw, 2)
                elif all(c in '01' for c in clean_vec) and len(clean_vec) > 1:
                    # Heuristic: If it contain ONLY 0s and 1s and is > 1 char, assume binary
                     vector = int(clean_vec, 2)
                else:
                    vector = int(vec_raw)
            else:
                vector = int(vec_raw)
            
            # Output path is the file path (unless it matches default 'results', then maybe treat as dir? 
            # But commonly single mode implies exact file path if provided, or dir if default.
            # If default "results" is used, we should probably generate a filename?
            # argparse default is "results". 
            
            if args.output_path == "results":
                # User didn't specify output path, so use default directory + auto naming?
                # Or just error out? 
                # Let's assume if it's the default directory, we construct a filename.
                output_dir = output_abs_path
                os.makedirs(output_dir, exist_ok=True)
                
                base_name = os.path.splitext(os.path.basename(input_path))[0]
                bin_full = f"{vector:016b}"
                binary_str = f"{bin_full[:8]}_{bin_full[8:]}"
                # Single mode default index 0
                filename = f"{base_name}_{binary_str}_0.scs"
                out_file = os.path.join(output_dir, filename)
                tasks.append((out_file, vector))
            else:
                # User specified a path. Is it a dir or file?
                # If it ends in .scs, assume file.
                if output_abs_path.endswith('.scs'):
                     tasks.append((output_abs_path, vector))
                else:
                    # Treat as directory
                    output_dir = output_abs_path
                    os.makedirs(output_dir, exist_ok=True)
                    base_name = os.path.splitext(os.path.basename(input_path))[0]
                    bin_full = f"{vector:016b}"
                    binary_str = f"{bin_full[:8]}_{bin_full[8:]}"
                    filename = f"{base_name}_{binary_str}_0.scs"
                    out_file = os.path.join(output_dir, filename)
                    tasks.append((out_file, vector))
            
        except ValueError:
            print("Error: Invalid error vector.")
            sys.exit(1)
    else:
        print("Error: Either --error_vector or --batch must be provided.")
        sys.exit(1)

    # Determine seed: Use provided or generate a random one
    # This ensuring EVERY run is reproducible if you check the logs/file header.
    if args.seed is not None:
        master_seed = args.seed
        print(f"Using provided Master Seed: {master_seed}")
    else:
        master_seed = random.randint(0, 2**32 - 1)
        print(f"No seed provided. Auto-generated Master Seed: {master_seed}")

    print(f"Processing '{input_path}' with {len(tasks)} generation tasks...")
    
    success_count = 0
    
    for i, (out_file, vector) in enumerate(tasks):
        try:
            # Use master_seed + index for deterministic variability
            task_seed = master_seed + i
            random.seed(task_seed)
                
            # Re-parse for each generation to ensure fresh state
            netlist_parser = NetlistParser(input_path)
            netlist_parser.parse()
            
            injector = ErrorInjector(netlist_parser)
            injector.inject(vector)
            
            bin_full = f"{vector:016b}"
            binary_str = f"{bin_full[:8]}_{bin_full[8:]}"
            
            # Construct new circuit name: {original_name}_{bin}_{index}
            filename_no_ext = os.path.splitext(os.path.basename(out_file))[0]
            new_circuit_name = filename_no_ext
            
            new_content = netlist_parser.regenerate(new_circuit_name=new_circuit_name)
            
            # Prepare Metadata Block
            date_str = os.popen('date').read().strip()
            # Format: 0000_0000_0000_0001
            # bin_full is 16 chars. binary_str is 8_8.
            vector_str = binary_str 
            
            metadata = [
                "* Generated By ASPECTOR Crucible",
                f"* Derivative Netlist: {os.path.basename(input_path)}",
                f"* Master Seed: {master_seed}",
                f"* Task Seed: {task_seed}",
                f"* Error Vector: {vector_str}",
                f"* Date: {date_str}",
                "" # Empty line
            ]
            metadata_block = "\n".join(metadata)
            
            # Inject metadata after *--- TOPOLOGY ---*
            if "*--- TOPOLOGY ---*" in new_content:
                new_content = new_content.replace("*--- TOPOLOGY ---*", f"*--- TOPOLOGY ---*\n\n{metadata_block}")
            else:
                # Fallback: Prepend if marker not found
                new_content = metadata_block + "\n" + new_content

            os.makedirs(os.path.dirname(out_file), exist_ok=True)
            with open(out_file, 'w') as f:
                f.write(new_content)
                
            print(f"  [OK] Saved to '{out_file}' (Vector: {vector})")
            success_count += 1
            
        except Exception as e:
            print(f"  [FAIL] Failed to generate '{out_file}': {e}")
            # traceback.print_exc()

    print(f"\nCompleted {success_count}/{len(tasks)} tasks.")

if __name__ == "__main__":
    main()
