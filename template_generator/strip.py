import re

def strip_ifs_and_elses(content, vars):
    """
    Process a template string with conditional directives based on variables.
    
    Handles directives:
    - %if(var)% ... %endif%
    - %if(var)% ... %else% ... %endif%
    - %if(var)% ... %elseif(var2)% ... %endif%
    - %if(var)% ... %elseif(var2)% ... %else% ... %endif%
    
    Args:
        content (str): The template content with conditional directives
        vars (dict): Dictionary of variable names and their values
        
    Returns:
        str: Processed content with conditional sections handled
    """
    import re
    
    # Stack to keep track of nested conditions and their truth values
    condition_stack = []
    
    # Find the start of each directive
    pos = 0
    result = ""
    
    # Regex patterns to match directives
    if_pattern = re.compile(r'%if\(([^)]+)\)%')
    elseif_pattern = re.compile(r'%elseif\(([^)]+)\)%')
    else_pattern = re.compile(r'%else%')
    endif_pattern = re.compile(r'%endif%')
    
    while pos < len(content):
        # Look for the next directive
        if_match = if_pattern.search(content, pos)
        elseif_match = elseif_pattern.search(content, pos)
        else_match = else_pattern.search(content, pos)
        endif_match = endif_pattern.search(content, pos)
        
        # Find the closest directive
        matches = [m for m in [if_match, elseif_match, else_match, endif_match] if m]
        if not matches:
            # No more directives, append the rest of the content
            if not condition_stack or condition_stack[-1]['include']:
                result += content[pos:]
            break
            
        next_match = min(matches, key=lambda m: m.start())
        
        # Process content before the directive
        if not condition_stack or condition_stack[-1]['include']:
            result += content[pos:next_match.start()]
        
        # Handle the directives
        if next_match == if_match:
            var_name = next_match.group(1)
            condition_value = var_name in vars and vars[var_name].lower() != "false" and vars[var_name] is not False
            include_content = condition_value
            condition_stack.append({
                'if_value': condition_value,
                'include': include_content,
                'branch_taken': condition_value
            })
        elif next_match == elseif_match:
            if not condition_stack:
                raise ValueError("Found %elseif% without matching %if%")
                
            var_name = next_match.group(1)
            condition_value = var_name in vars and vars[var_name] != "false" and vars[var_name] is not False
            
            # Only include this branch if the if condition was false and no previous branch was taken
            if not condition_stack[-1]['if_value'] and not condition_stack[-1]['branch_taken']:
                condition_stack[-1]['include'] = condition_value
                if condition_value:
                    condition_stack[-1]['branch_taken'] = True
            else:
                condition_stack[-1]['include'] = False
        elif next_match == else_match:
            if not condition_stack:
                raise ValueError("Found %else% without matching %if%")
                
            # Only include the else branch if no previous branch was taken
            condition_stack[-1]['include'] = not condition_stack[-1]['branch_taken']
        elif next_match == endif_match:
            if not condition_stack:
                raise ValueError("Found %endif% without matching %if%")
                
            condition_stack.pop()
        
        # Move past the directive
        pos = next_match.end()
    
    if condition_stack:
        raise ValueError("Unclosed conditional directive")
        
    return result