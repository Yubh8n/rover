#pragma once

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <std_msgs/msg/bool.hpp>
#include <cv_bridge/cv_bridge.hpp>
#include <tf2_ros/transform_broadcaster.h>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <message_filters/subscriber.h>
#include <message_filters/synchronizer.h>
#include <message_filters/sync_policies/approximate_time.h>

#include <opencv2/aruco.hpp>
#include <opencv2/aruco/charuco.hpp>
#include <opencv2/calib3d.hpp>

namespace vision
{

class ArucoNode : public rclcpp::Node
{
public:
  explicit ArucoNode(const rclcpp::NodeOptions & options = rclcpp::NodeOptions());

private:
  void syncCallback(
    const sensor_msgs::msg::Image::ConstSharedPtr & img_msg,
    const sensor_msgs::msg::CameraInfo::ConstSharedPtr & info_msg);

  void initBoard();
  bool detectAndEstimate(
    const cv::Mat & image,
    const cv::Mat & camera_matrix,
    const cv::Mat & dist_coeffs,
    cv::Vec3d & rvec,
    cv::Vec3d & tvec,
    cv::Mat & debug_image);

  int squares_x_;
  int squares_y_;
  float square_length_;
  float marker_length_;
  int dict_id_;
  int min_corners_;
  std::string board_frame_id_;
  std::string camera_frame_id_;
  bool publish_tf_;
  bool publish_debug_;

  cv::Ptr<cv::aruco::Dictionary>         dictionary_;
  cv::Ptr<cv::aruco::CharucoBoard>       board_;
  cv::Ptr<cv::aruco::DetectorParameters> detector_params_;

  rclcpp::Publisher<geometry_msgs::msg::PoseStamped>::SharedPtr pose_pub_;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr         debug_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr             detected_pub_;
  std::unique_ptr<tf2_ros::TransformBroadcaster>                tf_broadcaster_;

  using ImageSub      = message_filters::Subscriber<sensor_msgs::msg::Image>;
  using CameraInfoSub = message_filters::Subscriber<sensor_msgs::msg::CameraInfo>;
  using SyncPolicy    = message_filters::sync_policies::ApproximateTime<sensor_msgs::msg::Image, sensor_msgs::msg::CameraInfo>;
  using Sync          = message_filters::Synchronizer<SyncPolicy>;

  std::shared_ptr<ImageSub>      image_sub_;
  std::shared_ptr<CameraInfoSub> info_sub_;
  std::shared_ptr<Sync>          sync_;
};

} // namespace vision
