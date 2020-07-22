import boto3
import time
#modify the setting accourdingly 
#account details
AWS_ACCESS="AKIAIKCXN6MQGIO2Q6RQ"
AWS_SECRET="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"
AWS_REGION="us-east-1"
#instance details
VPCID = ""
PRIVATE_SUBNET_ID="" #private subnet for ec2
PUBLIC_SUBNET_IDS=["","",""] #public subnets for alb
IMAGE_ID="ami-08f3d892de259504d" #amazon linux 2 ami
INSTANCE_TYPE="t2.micro"
TARGETS_COUNT=2
ELB_PORT=80
TAG_NAME="hello-world-serivce"

user_data_script = """#!/bin/bash
sudo amazon-linux-extras install nginx1.12 -y
sudo systemctl start nginx
sudo echo "200 Hello World">/usr/share/nginx/html/index.html 
"""

class Infra(object):
    """
    Class to hold the logic of creating AWS Resources and python application.
    """

    def __init__(self):
        super(Infra, self).__init__()
        self.ec2SgId = set()
        self.lbSgId = set()
        self.EC2Ids = set()
        self.lbId = set()
        self.tgId = set()

    def run(self):
        self.session = self.get_session()
        self.create_sg()
        self.create_ec2()
        self.create_alb()
        self.create_alb_tg()
        self.register_target()
        self.create_listener()

    def get_session(self):
        """Gets a new boto3 session"""
        session = boto3.Session(region_name=AWS_REGION,
                              aws_access_key_id =AWS_ACCESS,
                              aws_secret_access_key=AWS_SECRET)
        return session

    def create_sg(self):
        """ creating ec2 security group """
        create_ec2_sg = self.session.client('ec2').create_security_group(
            GroupName='my_ec2_sg' ,
            Description='Allow traffic from alb',
            VpcId=VPCID
            )

        self.ec2SgId = create_ec2_sg['GroupId']
        
        """ creating alb security group """
        create_lb_sg = self.session.client('ec2').create_security_group(
            GroupName='load-balancer-sg',
            Description='Security Group for Internet-facing LB',
            VpcId=VPCID
            )

        self.lbSgId = create_lb_sg['GroupId']

        allow_ingress = self.session.client('ec2').authorize_security_group_ingress(
            GroupId=self.lbSgId,
            IpPermissions=[{"IpProtocol": "tcp", "FromPort": ELB_PORT, "ToPort": ELB_PORT, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]
            )

        """ allowing inbound to ec2 security group from alb security group """
        modify_ingress = self.session.client('ec2').authorize_security_group_ingress(
            GroupId=self.ec2SgId,
            IpPermissions=[{"IpProtocol": "tcp", "FromPort": ELB_PORT, "ToPort": ELB_PORT, 
            "UserIdGroupPairs": [{'Description': 'HTTP access from other instances','GroupId': self.lbSgId,},],}
            ])
        
    def create_ec2(self):
        reservation = self.session.client('ec2').run_instances(
            BlockDeviceMappings=[{
                'DeviceName': '/dev/xvda',
                'Ebs': {
                'DeleteOnTermination': True,
                'VolumeSize': 8,
                'VolumeType': 'gp2'
                },
            },],
            TagSpecifications=[{
            'ResourceType': 'instance',
            'Tags': [
                {
                    'Key': 'Name',
                    'Value': TAG_NAME
                },
            ]
        },
    ],
            UserData=user_data_script,
            ImageId=IMAGE_ID, InstanceType=INSTANCE_TYPE,
            MaxCount=TARGETS_COUNT, MinCount=TARGETS_COUNT,
            SecurityGroupIds=[self.ec2SgId], SubnetId=PRIVATE_SUBNET_ID)

        time.sleep(150)
        self.EC2Ids = [instance['InstanceId'] for instance in reservation['Instances']]
        print ("Created instances: " + ' '.join(p for p in self.EC2Ids))

    def create_alb(self):
        create_lb = self.session.client("elbv2").create_load_balancer(Name=TAG_NAME+'-alb',
                                                         Subnets=PUBLIC_SUBNET_IDS,
                                                         SecurityGroups=[self.lbSgId],
                                                         Scheme='internet-facing')

        self.lbId = create_lb['LoadBalancers'][0]['LoadBalancerArn']
        print("Successfully created load balancer %s" % self.lbId)

    def create_alb_tg(self):
        create_tg = self.session.client("elbv2").create_target_group(Name=TAG_NAME+'-tg',
                                                    Protocol='HTTP',
                                                    Port=ELB_PORT,
                                                    VpcId=VPCID)

        self.tgId = create_tg['TargetGroups'][0]['TargetGroupArn']
        print("Successfully created target group %s" % self.tgId)

    def register_target(self):
        ec2_list = [dict(Id=EC2Id, Port=ELB_PORT) for EC2Id in self.EC2Ids]
        reg_targets_response = self.session.client("elbv2").register_targets(TargetGroupArn=self.tgId, Targets=ec2_list)

    def create_listener(self):
        create_listener = self.session.client("elbv2").create_listener(LoadBalancerArn=self.lbId,
                                                      Protocol='HTTP', Port=ELB_PORT,
                                                      DefaultActions=[{'Type': 'forward',
                                                                       'TargetGroupArn': self.tgId}])

if __name__ == "__main__":
    infra = Infra()
    infra.run()
