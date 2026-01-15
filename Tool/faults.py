import random, string, sys


# B_Negate
def NegateBooleanValue(value_representation):
    try:
        value = bool(value_representation)
        return str(not value)
    except ValueError:
        pass
        
    return value_representation
    
    
# N_Add1
def Add1Unit(value_representation):
    try:
        value = int(value_representation)
        return str(value + 1)
    except ValueError:
        pass
    try:
        value = float(value_representation)
        return str(value + 1)
    except ValueError:
        pass
        
    return value_representation


# N_Sub1
def Subtract1Unit(value_representation):
    try:
        value = int(value_representation)
        return str(value - 1)
    except ValueError:
        pass
        
    try:
        value = float(value_representation)
        return str(value - 1)
    except ValueError:
        pass
        
    return value_representation
    
    
# N_RepPos
def ReplaceWithRandomPositive(value_representation):
    try:
        value = abs(float(value_representation))
        return str(random.uniform(value, value * 100)) 
    except ValueError:
        pass
        
    return value_representation


# N_RepNeg     
def ReplaceWithRandomNegative(value_representation):
    try:
        value = float(value_representation)
        if value < 0:
            return str(random.uniform(value * 100, value)) 
        else:
            return str(random.uniform(value * -100, value * -1))  
    except ValueError:
        pass
        
    return value_representation    


# N_Rep0   
def ReplaceWith0(value_representation):
    try:
        int(value_representation)
        return "0"
    except ValueError:
        pass
        
    try:
        float(value_representation)
        return "0.0"
    except ValueError:
        pass
        
    return value_representation


# N_Rep1
def ReplaceWith1(value_representation):
    try:
        int(value_representation)
        return "1"
    except ValueError:
        pass
        
    try:
        float(value_representation)
        return "1.0"
    except ValueError:
        pass
        
    return value_representation


# N_Rep-1   
def ReplaceWithMinus1(value_representation):
    try:
        int(value_representation)
        return "-1"
    except ValueError:
        pass
        
    try:
        float(value_representation)
        return "-1.0"
    except ValueError:
        pass
        
    return value_representation
    
    
# N_RepMax    
def ReplaceWithDataTypeMaximum(value_representation):
    try:
        value = float(value_representation)
        if value.is_integer():
            return str(sys.maxsize)
        else:
            return str(sys.float_info.max)
    except ValueError:
        pass
        
    return value_representation
    
    
# N_RepMin
def ReplaceWithDataTypeMinimum(value_representation):
    try:
        value = float(value_representation)
        if value.is_integer():
            return str(-sys.maxsize - 1)
        else:
            return str(-sys.float_info.max)
    except ValueError:
        pass
        
    return value_representation


# S_AppPrint 
def AddRandomCharactersToOverflowMaximumLength(value, maximum):
    if maximum > len(value):
        additional_characters = maximum - len(value)
        random_characters = ''.join(random.choices(string.printable, k=additional_characters))
        return value + random_characters
        
    return value
    
    
# S_RepPrint
def ReplaceWithRandomPrintableCharacterString(value):
    return ''.join(random.choices(string.printable, k=len(value)))    
    
    
# S_RepAlpha 
def ReplaceWithRandomAlphanumericString(value):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=len(value)))
  
  
# S_AppNPrint
def AddRandomNonPrintableCharactersToEnd(value, maximum):
    if len(value) < maximum:
        num_extra_chars = random.randint(1, maximum - len(value))
        extra_chars = ''.join(random.choice(string.printable) for _ in range(num_extra_chars))
        return value + extra_chars
        
    return value  
  
    
# S_InsNPrint
def InsertRandomNonPrintableCharactersAtRandomPositions(value, maximum):
    if maximum > len(value):
        for _ in range(maximum - len(value)):
            position = random.randint(0, len(value))
            value = value[:position] + random.choice(string.printable) + value[position:]
        
    return value


# S_RepNPrint
def ReplaceWithRandomNonPrintableCharacterString(value):
    return ''.join(random.choice(string.printable) if c.isprintable() else random.choice(string.printable) for c in value)


def test_faults(type_fault, value_representation, value_string, maximum):
    if type_fault == 'B_Negate':
        value = NegateBooleanValue(value_representation)
    elif type_fault == 'N_Add1':
        value = Add1Unit(value_representation)
    elif type_fault == 'N_Sub1':
        value = Subtract1Unit(value_representation)
    elif type_fault == 'N_RepPos':
        value = ReplaceWithRandomPositive(value_representation)
    elif type_fault == 'N_RepNeg':
        value = ReplaceWithRandomNegative(value_representation)
    elif type_fault == 'N_Rep0':
        value = ReplaceWith0(value_representation)
    elif type_fault == 'N_Rep1':
        value = ReplaceWith1(value_representation)
    elif type_fault == 'N_Rep_1':
        value = ReplaceWithMinus1(value_representation)
    elif type_fault == 'N_RepMax':
        value = ReplaceWithDataTypeMaximum(value_representation)
    elif type_fault == 'N_RepMin':
        value = ReplaceWithDataTypeMinimum(value_representation)
    elif type_fault == 'S_AppPrint':
        value = AddRandomCharactersToOverflowMaximumLength(value_string, maximum)
    elif type_fault == 'S_RepPrint':
        value = ReplaceWithRandomPrintableCharacterString(value_string)
    elif type_fault == 'S_RepAlpha':
        value = ReplaceWithRandomAlphanumericString(value_string)
    elif type_fault == 'S_AppNPrint':
        value = InsertRandomNonPrintableCharactersAtRandomPositions(value_string, maximum)
    elif type_fault == 'S_RepNPrint':
        value = ReplaceWithRandomNonPrintableCharacterString(value_string)
    elif type_fault == 'S_InsNPrint':
        value = AddRandomNonPrintableCharactersToEnd(value_string, maximum)
    else:
        raise ValueError("Invalid fault type specified")
    
    return value
