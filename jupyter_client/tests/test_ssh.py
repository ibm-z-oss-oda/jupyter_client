from jupyter_client.ssh.tunnel import select_specified_ports, select_random_ports

def test_random_ports():
    for i in range(4096):
        ports = select_random_ports(10)
        assert len(ports) == 10
        for p in ports:
            assert ports.count(p) == 1

def test_specified_ports():
    starting_port = 29031
    for i in range(5):
        ports = select_specified_ports(5,starting_port,5)
        starting_port += 5
        assert len(ports) == 5 
        for p in ports:
            assert ports.count(p) == 1
