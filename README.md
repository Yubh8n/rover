##Notes##

Når man kører ros2 over wifi, er der nogle gange brug for 
en fast DDS server da multicast ikke altid fungerer
så godt over wifi, kablet er fint men wifi er skrald.
for at starte en dds server på den pågældende maskine brug

`fastdds discovery -i 0 -p 11811`

For så at få forbindelse til den DDS server, brug

`export ROS_DISCOVERY_SERVER=192.168.73.141:11811`

selvfølgelig med den ip som dds serveren ligger på
ikke rode ved porten.

DDS-serveren kører på Pi'en (DDS.service), som kan findes med mDNS som `rover101.local`:

`export ROS_DISCOVERY_SERVER=rover101.local:11811`

`export ROS_SUPER_CLIENT=TRUE` (så `ros2 topic list` m.m. ser alle noder)

`ros2 topic list --no-daemon --spin-time 8` (giv discovery et par sekunder)



Der er åbenbart en flaskehals når man skal køre med højere opløsning og framerate.
Man kan sætte miljøvariablen FASTDDS_BUILTIN_TRANSPORTS=UDPv4 for at bruge UDP i stedet for TCP, hvilket kan give bedre performance.

`export FASTDDS_BUILTIN_TRANSPORTS=UDPv4`

To make the rover move with full speed:

`ros2 topic pub -1 /motor_speed std_msgs/msg/UInt8 "{data: 255}"`
