from template_generator.strip import strip_ifs_and_elses
import pytest

def test_ifs_and_elses():
    vars = {"sayhello": "Yes"}
    filecontents = "%if(sayhello)%hello%endif%"
    assert strip_ifs_and_elses(filecontents, vars) == "hello"
    vars["sayhello"] = "falSe"
    assert strip_ifs_and_elses(filecontents, vars) == ""
    vars = {}
    assert strip_ifs_and_elses(filecontents, vars) == ""
    filecontents = "%if(sayhello)%hello\n%else%bye%endif%"
    vars["sayhello"] = "false"
    assert strip_ifs_and_elses(filecontents, vars) == "bye"
    vars["sayhello"] = "true"
    assert strip_ifs_and_elses(filecontents, vars) == "hello\n"
    filecontents = "%if(sayhello)%hello\n%elseif(saybye)%bye%endif%"
    vars["sayhello"] = "false"
    vars["saybye"] = "true"
    assert strip_ifs_and_elses(filecontents, vars) == "bye"
    vars["sayhello"] = "true"
    assert strip_ifs_and_elses(filecontents, vars) == "hello\n"
    vars["saybye"] = "false"
    assert strip_ifs_and_elses(filecontents, vars) == "hello\n"
    vars["sayhello"] = "false"
    assert strip_ifs_and_elses(filecontents, vars) == ""
    filecontents = "%if(sayhello)%hello\n%elseif(saybye)%bye%elseif(sayhi)%hi%else%nothing%endif%"
    vars["sayhello"] = "false"
    vars["saybye"] = "false"
    vars["sayhi"] = "true"
    assert strip_ifs_and_elses(filecontents, vars) == "hi"
    vars["saybye"] = "true"
    assert strip_ifs_and_elses(filecontents, vars) == "bye"
    vars["sayhello"] = "true"
    assert strip_ifs_and_elses(filecontents, vars) == "hello\n"
    vars["saybye"] = "false"
    vars["sayhi"] = "false"
    vars["sayhello"] = "false"
    assert strip_ifs_and_elses(filecontents, vars) == "nothing"

def test_nested_ifs():
    vars = {"sayhello": "true"}
    filecontents = "%if(sayhello)%hello%if(sayhi)%hi%endif%world%endif%"
    assert strip_ifs_and_elses(filecontents, vars) == "helloworld"
    filecontents = "%if(whatever)%whatever%elseif(sayhello)%hello%if(sayhi)%hi%endif%world%endif%"
    assert strip_ifs_and_elses(filecontents, vars) == "helloworld"
    vars["sayhi"] = "Hei"
    assert strip_ifs_and_elses(filecontents, vars) == "hellohiworld"

def test_variables_do_not_interfere_with_ifs_and_elses():
    vars = {"sayhello": "true"}
    filecontents = "%if(sayhello)%%hello%%endif%"
    assert strip_ifs_and_elses(filecontents, vars) == "%hello%"

def test_raises_error_on_unbalanced_ifs():
    vars = {"sayhello": "true"}
    filecontents = "%if(sayhello)%hello%endif%%endif%"
    with pytest.raises(ValueError):
        strip_ifs_and_elses(filecontents, vars)

    filecontents = "%if(sayhello)%hello"
    with pytest.raises(ValueError):
        strip_ifs_and_elses(filecontents, vars)